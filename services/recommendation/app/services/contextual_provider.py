import asyncio
import logging
import typing

import app.cache
import app.config
import app.db
import app.services._language_boost
import app.services.author_recommender
import app.services.book_recommender
import app.services.list_builder
import app.services.personal_provider
import app.services.series_recommender
import sqlalchemy

logger = logging.getLogger(__name__)

_COLD_TIMEOUT = 2.5


async def _bulk_fetch_books(
    session_maker: typing.Any,
    book_ids: typing.List[int],
) -> typing.Dict[int, typing.Dict[str, typing.Any]]:
    async with session_maker() as session:
        result = await session.execute(
            sqlalchemy.text(
                f"SELECT {app.services.list_builder._BOOK_FIELDS}, 0 AS score "
                f"FROM books.books b "
                f"{app.services.list_builder._BOOK_JOINS} "
                f"WHERE b.book_id = ANY(:ids) "
                f"{app.services.list_builder._BOOK_GROUP_BY}"
            ),
            {"ids": book_ids},
        )
        return {
            row.book_id: app.services.list_builder._row_to_book_item(row, 0.0)
            for row in result
        }


async def _bulk_fetch_authors(
    session_maker: typing.Any,
    author_ids: typing.List[int],
) -> typing.Dict[int, typing.Dict[str, typing.Any]]:
    async with session_maker() as session:
        result = await session.execute(
            sqlalchemy.text(
                f"""
                WITH author_app_readers AS (
                    SELECT ba_r.author_id, COUNT(DISTINCT bs_a.user_id) AS app_readers
                    FROM user_data.bookshelves bs_a
                    JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
                    WHERE ba_r.author_id = ANY(:ids)
                    GROUP BY ba_r.author_id
                ),
                {app.services.list_builder.author_works_cte("ba.author_id = ANY(:ids)")}
                SELECT
                    a.author_id,
                    a.name,
                    a.slug,
                    COALESCE(a.photo_url, '') AS photo_url,
                    COUNT(DISTINCT aw.book_id) AS book_count,
                    COALESCE(
                        SUM(
                            COALESCE(aw.avg_rating::numeric, 0) * aw.rating_count
                            + COALESCE(aw.ol_avg_rating::numeric, 0) * aw.ol_rating_count
                        )
                        / NULLIF(SUM(aw.rating_count + aw.ol_rating_count), 0),
                        0
                    ) AS avg_rating,
                    COALESCE(SUM(aw.rating_count + aw.ol_rating_count), 0) AS rating_count,
                    COALESCE(
                        SUM(
                            COALESCE(aw.ol_want_to_read_count, 0) +
                            COALESCE(aw.ol_currently_reading_count, 0) +
                            COALESCE(aw.ol_already_read_count, 0)
                        ), 0
                    ) + COALESCE(aar.app_readers, 0) AS readers
                FROM books.authors a
                LEFT JOIN author_works aw ON aw.author_id = a.author_id
                LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
                WHERE a.author_id = ANY(:ids)
                GROUP BY a.author_id, a.name, a.slug, a.photo_url, aar.app_readers
                """
            ),
            {"ids": author_ids},
        )
        return {
            row.author_id: app.services.list_builder._row_to_author_item(row, 0.0)
            for row in result
        }


async def _read_precomputed(
    entity_type: str,
    entity_id: int,
    session_maker: typing.Any,
    limit: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    async with session_maker() as session:
        result = await session.execute(
            sqlalchemy.text(
                "SELECT section_key, display_name, similar_ids, title_params "
                "FROM recommendation.contextual_recs "
                "WHERE entity_type = :etype AND entity_id = :eid"
            ),
            {"etype": entity_type, "eid": entity_id},
        )
        precomputed_rows = result.fetchall()

    if not precomputed_rows:
        return None

    all_ids: typing.List[int] = []
    seen_ids: typing.Set[int] = set()
    for row in precomputed_rows:
        for eid in (row.similar_ids or [])[:limit]:
            if eid not in seen_ids:
                all_ids.append(eid)
                seen_ids.add(eid)

    if not all_ids:
        return []

    if entity_type == "author":
        items_by_id = await _bulk_fetch_authors(session_maker, all_ids)
    else:
        items_by_id = await _bulk_fetch_books(session_maker, all_ids)

    sections = []
    for row in precomputed_rows:
        ordered_ids = (row.similar_ids or [])[:limit]
        items = [items_by_id[i] for i in ordered_ids if i in items_by_id]
        if not items:
            continue
        if entity_type == "author":
            sections.append(
                {
                    "section_key": row.section_key,
                    "display_name": row.display_name,
                    "item_type": "author",
                    "author_items": items,
                    "total": len(items),
                    "title_params": row.title_params or {},
                }
            )
        else:
            # No language to prefer: precompute seeds one row per edition and
            # elects the edition through preferred_edition_sql, so the stored
            # ids already hold one language-correct edition per work. This call
            # is the net for that invariant breaking, and with no better
            # signal it keeps the most-read edition of any duplicated work.
            deduped = app.services._language_boost.dedupe_by_work(items, "")
            sections.append(
                {
                    "section_key": row.section_key,
                    "display_name": row.display_name,
                    "item_type": "book",
                    "book_items": deduped,
                    "total": len(deduped),
                    "title_params": row.title_params or {},
                }
            )

    return sections if sections else None


async def _build_minimal_book_fallback(
    session_maker: typing.Any,
    book_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    async def run(fn: typing.Callable, *args: typing.Any) -> typing.Any:
        async with session_maker() as session:
            return await fn(session, *args)

    async with session_maker() as session:
        metadata = await app.services.book_recommender._get_book_metadata(session, book_id)

    if metadata is None:
        return []

    language = metadata["language"]
    tasks = [
        run(app.services.book_recommender._build_more_by_author, book_id, limit, language)
    ]
    if metadata["series_id"] is not None:
        tasks.append(
            run(
                app.services.book_recommender._build_more_from_series,
                book_id,
                metadata["series_id"],
                limit,
                language,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    sections = []
    author_label = ", ".join(metadata["author_names"]) if metadata["author_names"] else ""

    if results[0] and not isinstance(results[0], Exception):
        deduped_author = app.services._language_boost.dedupe_by_work(results[0], language)
        display_author = author_label or "this author"
        sections.append(
            app.services.list_builder._make_book_section(
                "more_by_author", f"More by {display_author}", deduped_author,
                {"author": author_label} if author_label else {},
            )
        )

    if len(results) > 1 and results[1] and not isinstance(results[1], Exception):
        deduped_series = app.services._language_boost.dedupe_by_work(results[1], language)
        sections.append(
            app.services.list_builder._make_book_section(
                "more_from_series", f"More from {metadata['series_name']}", deduped_series,
                {"series": metadata["series_name"]},
            )
        )

    return sections


async def _build_minimal_author_fallback(
    session_maker: typing.Any,
    author_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    try:
        async with session_maker() as session:
            result = await asyncio.wait_for(
                app.services.author_recommender._build_similar_authors_by_genre(
                    session, author_id, limit
                ),
                timeout=_COLD_TIMEOUT,
            )
        if not result:
            return []
        return [
            app.services.author_recommender._make_author_section(
                "similar_authors", "Similar authors", result
            )
        ]
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"[rec:cold] author {author_id} fallback failed: {e}")
        return []


async def _build_minimal_series_fallback(
    session_maker: typing.Any,
    series_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    try:
        async with session_maker() as session:
            metadata = await app.services.series_recommender._get_series_metadata(
                session, series_id
            )
        if metadata is None:
            return []

        async with session_maker() as session:
            result = await asyncio.wait_for(
                app.services.series_recommender._build_more_by_author(
                    session,
                    series_id,
                    metadata["author_ids"],
                    limit,
                    metadata["language"],
                ),
                timeout=_COLD_TIMEOUT,
            )
        if not result:
            return []

        author_label = ", ".join(metadata["author_names"]) if metadata["author_names"] else ""
        display_author = author_label or "this author"
        return [
            app.services.list_builder._make_book_section(
                "more_by_author", f"More by {display_author}", result,
                {"author": author_label} if author_label else {},
            )
        ]
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"[rec:cold] series {series_id} fallback failed: {e}")
        return []


async def get_book_recommendations(
    book_id: int,
    limit_per_section: int,
    user_id: int = 0,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    if user_id > 0:
        return await _get_personal_book_sections(book_id, limit_per_section, user_id)

    cache_key = f"rec:book:{book_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    sections = await _read_precomputed("book", book_id, app.db.async_session_maker, limit_per_section)
    ttl = app.config.settings.cache_contextual_ttl

    if sections is None:
        sections = await _build_minimal_book_fallback(
            app.db.async_session_maker, book_id, limit_per_section
        )
        ttl = app.config.settings.contextual_cold_ttl

    if sections:
        await app.cache.set_cached(cache_key, sections, ttl)
    return sections


async def _get_personal_book_sections(
    book_id: int,
    limit_per_section: int,
    user_id: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    return await app.services.personal_provider.get_personal_book_sections(
        user_id, book_id, limit_per_section
    )


async def get_author_recommendations(
    author_id: int,
    limit_per_section: int,
    user_id: int = 0,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    if user_id > 0:
        return await _get_personal_author_sections(author_id, limit_per_section, user_id)

    cache_key = f"rec:author:{author_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    sections = await _read_precomputed(
        "author", author_id, app.db.async_session_maker, limit_per_section
    )
    ttl = app.config.settings.cache_contextual_ttl

    if sections is None:
        sections = await _build_minimal_author_fallback(
            app.db.async_session_maker, author_id, limit_per_section
        )
        ttl = app.config.settings.contextual_cold_ttl

    if sections:
        await app.cache.set_cached(cache_key, sections, ttl)
    return sections


async def _get_personal_author_sections(
    author_id: int,
    limit_per_section: int,
    user_id: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    return await app.services.personal_provider.get_personal_author_sections(
        user_id, author_id, limit_per_section
    )


async def get_series_recommendations(
    series_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    cache_key = f"rec:series:{series_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    sections = await _read_precomputed(
        "series", series_id, app.db.async_session_maker, limit_per_section
    )
    ttl = app.config.settings.cache_contextual_ttl

    if sections is None:
        sections = await _build_minimal_series_fallback(
            app.db.async_session_maker, series_id, limit_per_section
        )
        ttl = app.config.settings.contextual_cold_ttl

    if sections:
        await app.cache.set_cached(cache_key, sections, ttl)
    return sections
