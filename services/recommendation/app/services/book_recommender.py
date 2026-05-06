import asyncio
import logging
import typing

import app.services.list_builder
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def _get_book_metadata(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                b.book_id,
                b.title,
                b.series_id,
                s.name AS series_name,
                ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names
            FROM books.books b
            LEFT JOIN books.series s ON b.series_id = s.series_id
            LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
            LEFT JOIN books.authors a ON ba.author_id = a.author_id
            WHERE b.book_id = :book_id
            GROUP BY b.book_id, s.name
        """
        ),
        {"book_id": book_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return {
        "book_id": row.book_id,
        "title": row.title or "",
        "series_id": row.series_id,
        "series_name": row.series_name or "",
        "author_names": list(row.author_names or []),
    }



async def _build_more_by_author(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND b.book_id != :book_id
              AND ba.author_id IN (
                  SELECT ba2.author_id FROM books.book_authors ba2 WHERE ba2.book_id = :book_id
              )
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"book_id": book_id, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_more_from_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    series_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.series_position AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND b.book_id != :book_id
              AND b.series_id = :series_id
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.series_position ASC NULLS LAST
            LIMIT :limit
            """
        ),
        {"book_id": book_id, "series_id": series_id, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_similar_by_genre(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH source_genres AS (
                SELECT genre_id FROM books.book_genres WHERE book_id = :book_id
            ),
            source_count AS (
                SELECT COUNT(*) AS cnt FROM source_genres
            ),
            candidates AS (
                SELECT
                    bg.book_id,
                    COUNT(*) AS shared,
                    (SELECT cnt FROM source_count) AS source_cnt
                FROM books.book_genres bg
                JOIN source_genres sg ON bg.genre_id = sg.genre_id
                JOIN books.books bc ON bg.book_id = bc.book_id
                WHERE bg.book_id != :book_id
                  AND bc.language = 'en'
                  AND (COALESCE(bc.rating_count, 0) + COALESCE(bc.ol_rating_count, 0)) >= 50
                GROUP BY bg.book_id
                HAVING COUNT(*) >= 2
                ORDER BY shared DESC
                LIMIT 500
            ),
            candidate_genre_counts AS (
                SELECT bg2.book_id, COUNT(*) AS candidate_cnt
                FROM books.book_genres bg2
                JOIN candidates c ON c.book_id = bg2.book_id
                GROUP BY bg2.book_id
            )
            SELECT {app.services.list_builder._BOOK_FIELDS},
                   c.shared::float / NULLIF(
                       c.source_cnt + cgc.candidate_cnt - c.shared, 0
                   ) AS score
            FROM candidates c
            JOIN candidate_genre_counts cgc ON cgc.book_id = c.book_id
            JOIN books.books b ON c.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND c.shared > 0
            GROUP BY b.book_id, c.shared, c.source_cnt, c.book_id, cgc.candidate_cnt
            ORDER BY score DESC NULLS LAST, b.rating_count DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"book_id": book_id, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_readers_also_enjoyed(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH source_readers AS (
                SELECT DISTINCT user_id
                FROM user_data.bookshelves
                WHERE book_id = :book_id AND status IN ('read', 'reading')
                LIMIT 500
            ),
            co_books AS (
                SELECT bs.book_id, COUNT(DISTINCT bs.user_id) AS co_count
                FROM user_data.bookshelves bs
                JOIN source_readers sr ON bs.user_id = sr.user_id
                WHERE bs.book_id != :book_id
                  AND bs.status IN ('read', 'reading')
                GROUP BY bs.book_id
                HAVING COUNT(DISTINCT bs.user_id) >= 3
                ORDER BY co_count DESC
                LIMIT 500
            )
            SELECT {app.services.list_builder._BOOK_FIELDS}, cb.co_count AS score
            FROM co_books cb
            JOIN books.books b ON cb.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) >= 50
            GROUP BY b.book_id, cb.co_count
            ORDER BY cb.co_count DESC, b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"book_id": book_id, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]



def _make_book_section(
    section_key: str,
    display_name: str,
    items: typing.List[typing.Dict[str, typing.Any]],
) -> typing.Dict[str, typing.Any]:
    return {
        "section_key": section_key,
        "display_name": display_name,
        "item_type": "book",
        "book_items": items,
        "total": len(items),
    }


async def build_book_recommendations(
    session_maker: typing.Any,
    book_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    async def run(fn: typing.Callable, *args: typing.Any) -> typing.Any:
        async with session_maker() as session:
            return await fn(session, *args)

    async with session_maker() as session:
        metadata = await _get_book_metadata(session, book_id)
    if metadata is None:
        return None

    title = metadata["title"]
    series_id = metadata["series_id"]
    series_name = metadata["series_name"]
    author_names = metadata["author_names"]

    author_label = ", ".join(author_names) if author_names else "this author"

    tasks = [
        run(_build_more_by_author, book_id, limit_per_section),
        run(_build_similar_by_genre, book_id, limit_per_section),
        run(_build_readers_also_enjoyed, book_id, limit_per_section),
    ]
    if series_id is not None:
        tasks.append(run(_build_more_from_series, book_id, series_id, limit_per_section))

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    section_labels = ["more_by_author", "similar_by_genre", "readers_also_enjoyed"]
    for i, result in enumerate(all_results[:3]):
        if isinstance(result, Exception):
            logger.error(f"[rec:book:{book_id}] {section_labels[i]} failed: {result}")

    more_by_author_items = all_results[0] if not isinstance(all_results[0], Exception) else []
    similar_genre_items = all_results[1] if not isinstance(all_results[1], Exception) else []
    readers_enjoyed_items = all_results[2] if not isinstance(all_results[2], Exception) else []

    series_items: typing.List[typing.Dict] = []
    if series_id is not None:
        raw = all_results[3]
        if isinstance(raw, Exception):
            logger.error(f"[rec:book:{book_id}] more_from_series failed: {raw}")
        else:
            series_items = raw

    sections: typing.List[typing.Dict[str, typing.Any]] = []

    if more_by_author_items:
        sections.append(_make_book_section("more_by_author", f"More by {author_label}", more_by_author_items))

    if series_items:
        sections.append(_make_book_section("more_from_series", f"More from {series_name}", series_items))

    if similar_genre_items:
        sections.append(_make_book_section("similar_by_genre", f"Similar to {title}", similar_genre_items))

    if readers_enjoyed_items:
        sections.append(_make_book_section("readers_also_enjoyed", "Readers also enjoyed", readers_enjoyed_items))

    return sections
