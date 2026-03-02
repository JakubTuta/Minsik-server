import asyncio
import logging
import typing

import app.services.list_builder
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_SUB_RATING_DIMENSIONS: typing.Dict[str, str] = {
    "emotional_impact": "Similarly moving",
    "intellectual_depth": "Similarly thought-provoking",
    "writing_quality": "Similarly well-written",
    "rereadability": "Similarly rereadable",
    "pacing": "Similarly paced",
    "readability": "Similarly challenging",
    "plot_complexity": "Similarly complex",
    "humor": "Similarly funny",
}

_DIMENSION_THRESHOLD = 4.0
_DIMENSION_MIN_COUNT = 3


async def _get_book_metadata(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text("""
            SELECT
                b.book_id,
                b.title,
                b.series_id,
                s.name AS series_name,
                b.sub_rating_stats,
                ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names
            FROM books.books b
            LEFT JOIN books.series s ON b.series_id = s.series_id
            LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
            LEFT JOIN books.authors a ON ba.author_id = a.author_id
            WHERE b.book_id = :book_id
            GROUP BY b.book_id, s.name
        """),
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
        "sub_rating_stats": row.sub_rating_stats or {},
        "author_names": list(row.author_names or []),
    }


def _determine_prominent_dimensions(
    sub_rating_stats: typing.Dict[str, typing.Any],
) -> typing.List[typing.Tuple[str, str, float]]:
    results = []
    for dimension, display_name in _SUB_RATING_DIMENSIONS.items():
        stats = sub_rating_stats.get(dimension)
        if not stats:
            continue
        avg_str = stats.get("avg")
        count_str = stats.get("count")
        if not avg_str or not count_str:
            continue
        try:
            avg_val = float(avg_str)
            count_val = int(count_str)
        except (ValueError, TypeError):
            continue
        if avg_val >= _DIMENSION_THRESHOLD and count_val >= _DIMENSION_MIN_COUNT:
            results.append((dimension, display_name, avg_val))
    return results


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
    return [app.services.list_builder._row_to_book_item(row, float(row.score or 0)) for row in result]


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
    return [app.services.list_builder._row_to_book_item(row, float(row.score or 0)) for row in result]


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
                WHERE bg.book_id != :book_id
                GROUP BY bg.book_id
            )
            SELECT {app.services.list_builder._BOOK_FIELDS},
                   c.shared::float / NULLIF(
                       c.source_cnt + (
                           SELECT COUNT(*) FROM books.book_genres bg2 WHERE bg2.book_id = c.book_id
                       ) - c.shared, 0
                   ) AS score
            FROM candidates c
            JOIN books.books b ON c.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND c.shared > 0
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY score DESC NULLS LAST, b.rating_count DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"book_id": book_id, "limit": limit},
    )
    return [app.services.list_builder._row_to_book_item(row, float(row.score or 0)) for row in result]


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
                HAVING COUNT(DISTINCT bs.user_id) >= 2
            )
            SELECT {app.services.list_builder._BOOK_FIELDS}, cb.co_count AS score
            FROM co_books cb
            JOIN books.books b ON cb.book_id = b.book_id
            {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY cb.co_count DESC, b.avg_rating DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"book_id": book_id, "limit": limit},
    )
    return [app.services.list_builder._row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_similar_by_dimension(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    dimension: str,
    target_value: float,
    limit: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT {app.services.list_builder._BOOK_FIELDS},
                   ABS(CAST(b.sub_rating_stats->'{dimension}'->>'avg' AS FLOAT) - :target_value) AS score
            FROM books.books b {app.services.list_builder._BOOK_JOINS}
            WHERE {app.services.list_builder._BOOK_BASE_WHERE}
              AND b.book_id != :book_id
              AND b.sub_rating_stats->'{dimension}'->>'count' IS NOT NULL
              AND CAST(b.sub_rating_stats->'{dimension}'->>'count' AS INTEGER) >= :min_count
              AND ABS(CAST(b.sub_rating_stats->'{dimension}'->>'avg' AS FLOAT) - :target_value) <= 0.5
            {app.services.list_builder._BOOK_GROUP_BY}
            ORDER BY score ASC, b.rating_count DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {
            "book_id": book_id,
            "target_value": target_value,
            "min_count": _DIMENSION_MIN_COUNT,
            "limit": limit,
        },
    )
    return [app.services.list_builder._row_to_book_item(row, float(row.score or 0)) for row in result]


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
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    metadata = await _get_book_metadata(session, book_id)
    if metadata is None:
        return None

    title = metadata["title"]
    series_id = metadata["series_id"]
    series_name = metadata["series_name"]
    author_names = metadata["author_names"]
    sub_rating_stats = metadata["sub_rating_stats"]

    author_label = ", ".join(author_names) if author_names else "this author"
    prominent_dimensions = _determine_prominent_dimensions(sub_rating_stats)

    always_tasks = [
        _build_more_by_author(session, book_id, limit_per_section),
        _build_similar_by_genre(session, book_id, limit_per_section),
        _build_readers_also_enjoyed(session, book_id, limit_per_section),
    ]
    dimension_tasks = [
        _build_similar_by_dimension(session, book_id, dim, avg_val, limit_per_section)
        for dim, _, avg_val in prominent_dimensions
    ]

    all_results = await asyncio.gather(
        *always_tasks,
        *(
            [_build_more_from_series(session, book_id, series_id, limit_per_section)]
            if series_id is not None
            else []
        ),
        *dimension_tasks,
        return_exceptions=True,
    )

    more_by_author_items, similar_genre_items, readers_enjoyed_items = (
        all_results[0] if not isinstance(all_results[0], Exception) else [],
        all_results[1] if not isinstance(all_results[1], Exception) else [],
        all_results[2] if not isinstance(all_results[2], Exception) else [],
    )

    idx = 3
    series_items: typing.List[typing.Dict] = []
    if series_id is not None:
        raw = all_results[idx]
        series_items = raw if not isinstance(raw, Exception) else []
        idx += 1

    dimension_results = []
    for i, (dim, display_name, _) in enumerate(prominent_dimensions):
        raw = all_results[idx + i]
        dimension_results.append((dim, display_name, raw if not isinstance(raw, Exception) else []))

    sections: typing.List[typing.Dict[str, typing.Any]] = []

    if more_by_author_items:
        sections.append(_make_book_section(
            "more_by_author",
            f"More by {author_label}",
            more_by_author_items,
        ))

    if series_items:
        sections.append(_make_book_section(
            "more_from_series",
            f"More from {series_name}",
            series_items,
        ))

    if similar_genre_items:
        sections.append(_make_book_section(
            "similar_by_genre",
            f"Similar to {title}",
            similar_genre_items,
        ))

    if readers_enjoyed_items:
        sections.append(_make_book_section(
            "readers_also_enjoyed",
            "Readers also enjoyed",
            readers_enjoyed_items,
        ))

    for dim, display_name, items in dimension_results:
        if items:
            sections.append(_make_book_section(
                f"similar_{dim}",
                display_name,
                items,
            ))

    return sections
