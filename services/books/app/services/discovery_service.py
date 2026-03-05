import logging
import typing

import app.services.book_service
import sqlalchemy.ext.asyncio
from sqlalchemy import text

logger = logging.getLogger(__name__)

MOOD_RATING_THRESHOLD = 3.5
MOOD_MIN_RATING_COUNT = 3
POPULAR_READER_THRESHOLD = 100
HIDDEN_GEM_MAX_READERS = 50
HIDDEN_GEM_MIN_RATING = 3.5

MOOD_TO_JSONB_KEY: typing.Dict[str, str] = {
    "funny": "humor",
    "emotional": "emotional_impact",
    "intellectual": "intellectual_depth",
    "easy_read": "readability",
    "complex": "plot_complexity",
    "fast_paced": "pacing",
}

BOOK_LENGTH_FILTERS: typing.Dict[str, str] = {
    "short": "b.number_of_pages IS NOT NULL AND b.number_of_pages < 200",
    "medium": "b.number_of_pages IS NOT NULL AND b.number_of_pages >= 200 AND b.number_of_pages <= 400",
    "long": "b.number_of_pages IS NOT NULL AND b.number_of_pages > 400 AND b.number_of_pages <= 600",
    "epic": "b.number_of_pages IS NOT NULL AND b.number_of_pages > 600",
}

ERA_FILTERS: typing.Dict[str, str] = {
    "classic": "b.original_publication_year IS NOT NULL AND b.original_publication_year < 1950",
    "modern": "b.original_publication_year IS NOT NULL AND b.original_publication_year >= 1950 AND b.original_publication_year < 2000",
    "contemporary": "b.original_publication_year IS NOT NULL AND b.original_publication_year >= 2000",
}

_COMBINED_RATING_EXPR = (
    "(COALESCE(b.avg_rating::numeric, 0) * b.rating_count"
    " + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count)::numeric"
    " / NULLIF(b.rating_count + b.ol_rating_count, 0)"
)

_TOTAL_READERS_EXPR = (
    "(b.ol_want_to_read_count + b.ol_currently_reading_count + b.ol_already_read_count"
    " + COALESCE(bs.minsik_readers, 0))"
)

_DISCOVERY_SELECT = f"""
    SELECT
        b.book_id,
        b.slug,
        {_COMBINED_RATING_EXPR} AS combined_rating,
        {_TOTAL_READERS_EXPR} AS total_readers
    FROM books.books b
    LEFT JOIN (
        SELECT book_id, COUNT(*) AS minsik_readers
        FROM user_data.bookshelves
        WHERE status != 'abandoned'
        GROUP BY book_id
    ) bs ON b.book_id = bs.book_id
"""

_DISCOVERY_GROUP_BY = """
    GROUP BY b.book_id, b.slug, b.avg_rating, b.rating_count,
             b.ol_avg_rating, b.ol_rating_count,
             b.ol_want_to_read_count, b.ol_currently_reading_count,
             b.ol_already_read_count, bs.minsik_readers
"""


async def discover_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    genre_slugs: typing.List[str],
    book_length: str,
    quality: str,
    moods: typing.List[str],
    era: str,
    series_filter: str,
    popularity: str,
    exclude_ids: typing.List[int],
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    where_clauses, having_clauses, params = _build_filter_clauses(
        language, genre_slugs, book_length, quality, moods, era,
        series_filter, popularity, exclude_ids,
    )

    matching_count = await _count_matching_books(session, where_clauses, having_clauses, params)

    if matching_count == 0:
        return None

    book_slug = await _fetch_random_matching_book(session, where_clauses, having_clauses, params)

    if book_slug is None:
        return None

    book_detail = await app.services.book_service.get_book_by_slug(session, book_slug, language)

    if book_detail is None:
        return None

    return {
        "book": book_detail,
        "matching_count": matching_count,
    }


def _build_filter_clauses(
    language: str,
    genre_slugs: typing.List[str],
    book_length: str,
    quality: str,
    moods: typing.List[str],
    era: str,
    series_filter: str,
    popularity: str,
    exclude_ids: typing.List[int],
) -> typing.Tuple[typing.List[str], typing.List[str], typing.Dict[str, typing.Any]]:
    where_clauses: typing.List[str] = []
    having_clauses: typing.List[str] = []
    params: typing.Dict[str, typing.Any] = {}

    where_clauses.append("b.language = :language")
    params["language"] = language

    where_clauses.append("b.primary_cover_url IS NOT NULL AND b.primary_cover_url != ''")

    if exclude_ids:
        where_clauses.append("b.book_id != ALL(:exclude_ids)")
        params["exclude_ids"] = exclude_ids

    if book_length and book_length in BOOK_LENGTH_FILTERS:
        where_clauses.append(BOOK_LENGTH_FILTERS[book_length])

    if era and era in ERA_FILTERS:
        where_clauses.append(ERA_FILTERS[era])

    if series_filter == "standalone":
        where_clauses.append("b.series_id IS NULL")
    elif series_filter == "series":
        where_clauses.append("b.series_id IS NOT NULL")

    if genre_slugs:
        where_clauses.append(
            "EXISTS ("
            "SELECT 1 FROM books.book_genres bg2"
            " JOIN books.genres g2 ON bg2.genre_id = g2.genre_id"
            " WHERE bg2.book_id = b.book_id AND g2.slug = ANY(:genre_slugs)"
            ")"
        )
        params["genre_slugs"] = genre_slugs

    if quality == "high":
        where_clauses.append("(b.rating_count + b.ol_rating_count) > 0")
        having_clauses.append(f"{_COMBINED_RATING_EXPR} > 4.0")
    elif quality == "medium":
        where_clauses.append("(b.rating_count + b.ol_rating_count) > 0")
        having_clauses.append(f"{_COMBINED_RATING_EXPR} > 3.0 AND {_COMBINED_RATING_EXPR} <= 4.0")
    elif quality == "low":
        where_clauses.append("(b.rating_count + b.ol_rating_count) > 0")
        having_clauses.append(f"{_COMBINED_RATING_EXPR} > 2.0 AND {_COMBINED_RATING_EXPR} <= 3.0")
    elif quality == "very_low":
        where_clauses.append("(b.rating_count + b.ol_rating_count) > 0")
        having_clauses.append(f"{_COMBINED_RATING_EXPR} <= 2.0")

    for mood in moods:
        jsonb_key = MOOD_TO_JSONB_KEY.get(mood)
        if jsonb_key:
            param_threshold = f"mood_threshold_{jsonb_key}"
            param_min_count = f"mood_min_count_{jsonb_key}"
            where_clauses.append(
                f"(b.sub_rating_stats->'{jsonb_key}'->>'avg')::numeric >= :{param_threshold}"
                f" AND (b.sub_rating_stats->'{jsonb_key}'->>'count')::int >= :{param_min_count}"
            )
            params[param_threshold] = MOOD_RATING_THRESHOLD
            params[param_min_count] = MOOD_MIN_RATING_COUNT

    if popularity == "popular":
        having_clauses.append(f"{_TOTAL_READERS_EXPR} > :popular_threshold")
        params["popular_threshold"] = POPULAR_READER_THRESHOLD
    elif popularity == "hidden_gem":
        where_clauses.append("(b.rating_count + b.ol_rating_count) > 0")
        having_clauses.append(f"{_TOTAL_READERS_EXPR} < :gem_max_readers")
        having_clauses.append(f"{_COMBINED_RATING_EXPR} > :gem_min_rating")
        params["gem_max_readers"] = HIDDEN_GEM_MAX_READERS
        params["gem_min_rating"] = HIDDEN_GEM_MIN_RATING

    return where_clauses, having_clauses, params


async def _count_matching_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    where_clauses: typing.List[str],
    having_clauses: typing.List[str],
    params: typing.Dict[str, typing.Any],
) -> int:
    inner_query = _DISCOVERY_SELECT
    if where_clauses:
        inner_query += " WHERE " + " AND ".join(where_clauses)
    inner_query += _DISCOVERY_GROUP_BY
    if having_clauses:
        inner_query += " HAVING " + " AND ".join(having_clauses)

    count_query = f"SELECT COUNT(*) FROM ({inner_query}) AS filtered"
    result = await session.execute(text(count_query), params)
    return result.scalar() or 0


async def _fetch_random_matching_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    where_clauses: typing.List[str],
    having_clauses: typing.List[str],
    params: typing.Dict[str, typing.Any],
) -> typing.Optional[str]:
    query = _DISCOVERY_SELECT
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += _DISCOVERY_GROUP_BY
    if having_clauses:
        query += " HAVING " + " AND ".join(having_clauses)
    query += " ORDER BY RANDOM() LIMIT 1"

    result = await session.execute(text(query), params)
    row = result.first()
    return row.slug if row is not None else None
