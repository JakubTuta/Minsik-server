import asyncio
import logging
import typing

import app.services.list_builder
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def _get_series_metadata(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                s.series_id,
                s.name,
                ARRAY_AGG(DISTINCT ba.author_id) FILTER (WHERE ba.author_id IS NOT NULL) AS author_ids,
                ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names
            FROM books.series s
            LEFT JOIN books.books b ON b.series_id = s.series_id
            LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
            LEFT JOIN books.authors a ON ba.author_id = a.author_id
            WHERE s.series_id = :series_id
            GROUP BY s.series_id, s.name
        """
        ),
        {"series_id": series_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return {
        "series_id": row.series_id,
        "name": row.name or "",
        "author_ids": list(row.author_ids or []),
        "author_names": list(row.author_names or []),
    }


async def _build_more_by_author(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    author_ids: typing.List[int],
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    if not author_ids:
        return []
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS}, b.avg_rating AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND (b.series_id IS NULL OR b.series_id != :series_id)
              AND EXISTS (
                  SELECT 1 FROM books.book_authors ba2
                  WHERE ba2.book_id = b.book_id
                    AND ba2.author_id = ANY(CAST(:author_ids AS bigint[]))
              )
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"series_id": series_id, "author_ids": author_ids, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_similar_by_genre(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH series_genres AS (
                SELECT DISTINCT bg.genre_id
                FROM books.book_genres bg
                JOIN books.books b ON bg.book_id = b.book_id
                WHERE b.series_id = :series_id
            ),
            source_count AS (
                SELECT COUNT(*) AS cnt FROM series_genres
            ),
            candidates AS (
                SELECT
                    bg.book_id,
                    COUNT(*) AS shared,
                    (SELECT cnt FROM source_count) AS source_cnt
                FROM books.book_genres bg
                JOIN series_genres sg ON bg.genre_id = sg.genre_id
                WHERE bg.book_id NOT IN (
                    SELECT b2.book_id FROM books.books b2 WHERE b2.series_id = :series_id
                )
                GROUP BY bg.book_id
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
        {"series_id": series_id, "limit": limit},
    )
    return [
        app.services.list_builder._row_to_book_item(row, float(row.score or 0))
        for row in result
    ]


async def _build_readers_also_enjoyed(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            WITH series_readers AS (
                SELECT DISTINCT bs.user_id
                FROM user_data.bookshelves bs
                JOIN books.books b ON bs.book_id = b.book_id
                WHERE b.series_id = :series_id AND bs.status IN ('read', 'reading')
                LIMIT 500
            ),
            co_books AS (
                SELECT bs.book_id, COUNT(DISTINCT bs.user_id) AS co_count
                FROM user_data.bookshelves bs
                JOIN series_readers sr ON bs.user_id = sr.user_id
                WHERE bs.status IN ('read', 'reading')
                  AND bs.book_id NOT IN (
                      SELECT b2.book_id FROM books.books b2 WHERE b2.series_id = :series_id
                  )
                GROUP BY bs.book_id
                HAVING COUNT(DISTINCT bs.user_id) >= 2
            )
            SELECT {app.services.list_builder._BOOK_FIELDS}, cb.co_count AS score
            FROM co_books cb
            JOIN books.books b ON cb.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
            GROUP BY b.book_id, cb.co_count
            ORDER BY cb.co_count DESC, b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"series_id": series_id, "limit": limit},
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


async def build_series_recommendations(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    metadata = await _get_series_metadata(session, series_id)
    if metadata is None:
        return None

    series_name = metadata["name"]
    author_ids = metadata["author_ids"]
    author_names = metadata["author_names"]
    author_label = ", ".join(author_names) if author_names else "this author"

    more_by_author_result, similar_genre_result, readers_enjoyed_result = (
        await asyncio.gather(
            _build_more_by_author(session, series_id, author_ids, limit_per_section),
            _build_similar_by_genre(session, series_id, limit_per_section),
            _build_readers_also_enjoyed(session, series_id, limit_per_section),
            return_exceptions=True,
        )
    )

    if isinstance(more_by_author_result, Exception):
        logger.error(
            f"[rec:series:{series_id}] more_by_author failed: {more_by_author_result}"
        )
    if isinstance(similar_genre_result, Exception):
        logger.error(
            f"[rec:series:{series_id}] similar_by_genre failed: {similar_genre_result}"
        )
    if isinstance(readers_enjoyed_result, Exception):
        logger.error(
            f"[rec:series:{series_id}] readers_also_enjoyed failed: {readers_enjoyed_result}"
        )

    sections: typing.List[typing.Dict[str, typing.Any]] = []

    if more_by_author_result and not isinstance(more_by_author_result, Exception):
        sections.append(
            _make_book_section(
                "more_by_author",
                f"More by {author_label}",
                more_by_author_result,
            )
        )

    if similar_genre_result and not isinstance(similar_genre_result, Exception):
        sections.append(
            _make_book_section(
                "similar_by_genre",
                f"Similar to {series_name}",
                similar_genre_result,
            )
        )

    if readers_enjoyed_result and not isinstance(readers_enjoyed_result, Exception):
        sections.append(
            _make_book_section(
                "readers_also_enjoyed",
                "Readers also enjoyed",
                readers_enjoyed_result,
            )
        )

    return sections
