import asyncio
import logging
import typing

import app.config
import app.services.author_recommender
import app.services.book_recommender
import app.services.series_recommender
import sqlalchemy
import sqlalchemy.engine
import sqlalchemy.orm

logger = logging.getLogger(__name__)

_SEMAPHORE_SIZE = 2
_BATCH_SIZE = 500
_PER_ENTITY_TIMEOUT = 10.0


async def _fetch_popular_book_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    min_ratings: int,
) -> typing.List[int]:
    # One seed per popular EDITION, not per work: book_recommender filters
    # candidates to the seed's own language, so a work's English and Polish
    # editions get distinct, language-correct precomputed sections rather
    # than only the English edition being fast-pathed and every other
    # edition falling back to a live query on every request.
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT book_id
            FROM books.books
            WHERE (COALESCE(rating_count, 0) + COALESCE(ol_rating_count, 0)) >= :min
              AND primary_cover_url IS NOT NULL
            """
        ),
        {"min": min_ratings},
    )
    return [row.book_id for row in result]


async def _fetch_popular_author_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    min_ratings: int,
) -> typing.List[int]:
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT ba.author_id
            FROM books.book_authors ba
            JOIN books.books b ON ba.book_id = b.book_id
            GROUP BY ba.author_id
            HAVING SUM(COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) >= :min
            """
        ),
        {"min": min_ratings},
    )
    return [row.author_id for row in result]


async def _fetch_popular_series_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    min_ratings: int,
) -> typing.List[int]:
    result = await session.execute(
        sqlalchemy.text(
            "SELECT DISTINCT b.series_id FROM books.books b "
            "WHERE b.series_id IS NOT NULL "
            "AND (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) >= :min"
        ),
        {"min": min_ratings},
    )
    return [row.series_id for row in result]


def _extract_section_rows(
    entity_type: str,
    entity_id: int,
    sections: typing.List[typing.Dict[str, typing.Any]],
) -> typing.List[typing.Dict[str, typing.Any]]:
    rows = []
    for section in sections:
        items = section.get("book_items") or section.get("author_items") or []
        similar_ids = []
        for item in items:
            eid = item.get("book_id") or item.get("author_id")
            if eid:
                similar_ids.append(eid)
        if not similar_ids:
            continue
        rows.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "section_key": section["section_key"],
                "display_name": section.get("display_name", ""),
                "similar_ids": similar_ids,
            }
        )
    return rows


async def _upsert_batch(
    session_maker: typing.Any,
    rows: typing.List[typing.Dict[str, typing.Any]],
) -> None:
    if not rows:
        return
    async with session_maker() as session:
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO recommendation.contextual_recs
                    (entity_type, entity_id, section_key, display_name, similar_ids)
                VALUES (:entity_type, :entity_id, :section_key, :display_name, :similar_ids)
                ON CONFLICT (entity_type, entity_id, section_key)
                DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    similar_ids  = EXCLUDED.similar_ids,
                    computed_at  = now()
                """
            ),
            rows,
        )
        await session.commit()


async def _reconcile_sections(
    session_maker: typing.Any,
    entity_type: str,
    reconcile_items: typing.List[typing.Tuple[int, typing.Set[str]]],
) -> None:
    if not reconcile_items:
        return
    params = [
        {"entity_type": entity_type, "entity_id": eid, "keys": list(keys)}
        for eid, keys in reconcile_items
    ]
    async with session_maker() as session:
        await session.execute(
            sqlalchemy.text(
                """
                DELETE FROM recommendation.contextual_recs
                WHERE entity_type = :entity_type
                  AND entity_id = :entity_id
                  AND NOT (section_key = ANY(CAST(:keys AS text[])))
                """
            ),
            params,
        )
        await session.commit()


async def _precompute_entities(
    entity_type: str,
    entity_ids: typing.List[int],
    builder_fn: typing.Callable,
    session_maker: typing.Any,
    limit: int,
) -> None:
    if not entity_ids:
        return

    sem = asyncio.Semaphore(_SEMAPHORE_SIZE)
    batch: typing.List[typing.Dict[str, typing.Any]] = []
    reconcile_items: typing.List[typing.Tuple[int, typing.Set[str]]] = []
    success = 0

    async def _one(eid: int) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
        async with sem:
            try:
                sections = await asyncio.wait_for(
                    builder_fn(session_maker, eid, limit),
                    timeout=_PER_ENTITY_TIMEOUT,
                )
                return _extract_section_rows(entity_type, eid, sections) if sections else []
            except asyncio.TimeoutError:
                logger.warning(
                    f"[rec:precompute] {entity_type} {eid} timed out after "
                    f"{_PER_ENTITY_TIMEOUT}s, skipping"
                )
            except Exception as e:
                logger.error(f"[rec:precompute] {entity_type} {eid} failed: {e}")
            return None

    chunk_size = 100
    total = len(entity_ids)

    for chunk_start in range(0, total, chunk_size):
        chunk = entity_ids[chunk_start : chunk_start + chunk_size]
        results = await asyncio.gather(*(_one(eid) for eid in chunk))
        for eid, rows in zip(chunk, results):
            if rows is None:
                continue
            success += 1
            reconcile_items.append((eid, {r["section_key"] for r in rows}))
            if rows:
                batch.extend(rows)
            if len(batch) >= _BATCH_SIZE:
                await _upsert_batch(session_maker, batch)
                batch = []

    if batch:
        await _upsert_batch(session_maker, batch)

    await _reconcile_sections(session_maker, entity_type, reconcile_items)

    logger.info(f"[rec:precompute] {entity_type}: {success}/{total} entities precomputed")


async def _cleanup_stale_rows(session_maker: typing.Any) -> int:
    async with session_maker() as session:
        result = await session.execute(
            sqlalchemy.text(
                """
                DELETE FROM recommendation.contextual_recs cr
                WHERE (
                    cr.entity_type = 'book'
                    AND NOT EXISTS (SELECT 1 FROM books.books b WHERE b.book_id = cr.entity_id)
                )
                OR (
                    cr.entity_type = 'author'
                    AND NOT EXISTS (SELECT 1 FROM books.authors a WHERE a.author_id = cr.entity_id)
                )
                OR (
                    cr.entity_type = 'series'
                    AND NOT EXISTS (SELECT 1 FROM books.series s WHERE s.series_id = cr.entity_id)
                )
                OR (
                    cr.entity_type = 'book'
                    AND cr.section_key = 'more_from_series'
                    AND NOT EXISTS (
                        SELECT 1 FROM books.books b
                        WHERE b.book_id = cr.entity_id AND b.series_id IS NOT NULL
                    )
                )
                """
            )
        )
        await session.commit()
        deleted = typing.cast(sqlalchemy.engine.CursorResult, result).rowcount
        return deleted if deleted and deleted > 0 else 0


async def refresh_contextual_recs(session_maker: sqlalchemy.orm.sessionmaker) -> None:
    settings = app.config.settings
    min_ratings = settings.contextual_precompute_min_ratings
    limit = 20

    logger.info("[rec:precompute] Starting contextual precompute refresh")

    stale_deleted = await _cleanup_stale_rows(session_maker)
    if stale_deleted:
        logger.info(f"[rec:precompute] Cleaned up {stale_deleted} stale contextual_recs rows")

    async with session_maker() as session:
        book_ids = await _fetch_popular_book_ids(session, min_ratings)
        author_ids = await _fetch_popular_author_ids(session, min_ratings)
        series_ids = await _fetch_popular_series_ids(session, min_ratings)

    logger.info(
        f"[rec:precompute] Entities to precompute — "
        f"books: {len(book_ids)}, authors: {len(author_ids)}, series: {len(series_ids)}"
    )

    await _precompute_entities(
        "book",
        book_ids,
        app.services.book_recommender.build_book_recommendations,
        session_maker,
        limit,
    )
    await _precompute_entities(
        "author",
        author_ids,
        app.services.author_recommender.build_author_recommendations,
        session_maker,
        limit,
    )
    await _precompute_entities(
        "series",
        series_ids,
        app.services.series_recommender.build_series_recommendations,
        session_maker,
        limit,
    )

    logger.info("[rec:precompute] Contextual precompute refresh complete")
