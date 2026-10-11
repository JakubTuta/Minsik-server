import hashlib
import json
import logging
import random
import time
import typing

import app.cache
import sqlalchemy
import sqlalchemy.ext.asyncio
import app.services._language_boost
import app.services._row_helpers

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
    " + COALESCE(wsc.readers, 0))"
)

# Every filter is a plain predicate on one row of books.books (plus the per-work shelf
# rollup for the popularity filters), so there is nothing to GROUP BY: the old
# GROUP BY/HAVING version aggregated one row per group of one.
_DISCOVERY_FROM = "FROM books.books b"
_DISCOVERY_FROM_WITH_SHELVES = f"""
    FROM books.books b
    {app.services._language_boost.work_shelf_counts_join()}
"""

# Below this many matching works the filter is selective enough that walking the key
# from a random point would read most of the table to find a row; the exact pick over
# the filtered set is cheaper and equally uniform.
PROBE_MIN_MATCHES = 2000

COUNT_CACHE_TTL_SECONDS = 600
BOUNDS_CACHE_TTL_SECONDS = 60

_bounds_cache: typing.Dict[str, typing.Any] = {"expires": 0.0, "low": 1, "high": 1}


_BOOK_SUMMARY_SELECT = f"""
    SELECT
        b.book_id,
        b.title,
        b.slug,
        b.description,
        b.primary_cover_url,
        b.rating_count,
        b.avg_rating,
        b.ol_rating_count,
        b.ol_avg_rating,
        b.ol_want_to_read_count,
        b.ol_currently_reading_count,
        b.ol_already_read_count,
        COALESCE(wsc.want_to_read_count, 0) AS app_want_to_read_count,
        COALESCE(wsc.reading_count, 0) AS app_reading_count,
        COALESCE(wsc.read_count, 0) AS app_read_count,
        (
            SELECT COALESCE(json_agg(json_build_object(
                'author_id', a2.author_id,
                'name', a2.name,
                'slug', a2.slug,
                'photo_url', a2.photo_url
            )), '[]'::json)
            FROM books.book_authors ba2
            JOIN books.authors a2 ON ba2.author_id = a2.author_id
            WHERE ba2.book_id = b.book_id
        ) AS authors
    FROM books.books b
    {app.services._language_boost.work_shelf_counts_join()}
    WHERE b.book_id = :book_id
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
    filters = _build_filter_clauses(
        genre_slugs, book_length, quality, moods, era, series_filter, popularity
    )

    matching_count = await _cached_matching_count(session, filters) - len(exclude_ids)
    if matching_count <= 0:
        return None

    book_id = await _pick_random_book(session, filters, language, exclude_ids, matching_count)
    if book_id is None:
        return None

    book_summary = await _fetch_book_summary_by_id(session, book_id)

    if book_summary is None:
        return None

    return {
        "book": book_summary,
        "matching_count": matching_count,
    }


async def count_matching_books(
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
) -> int:
    """Count-only variant for the live "X books match" chip while filtering.

    Filters are adjusted far more often than "Discover" is clicked, and each
    change re-runs this debounced. Reuses `discover_book`'s filtered scan
    without its random pick or book-detail fetch, which used to run the same
    full DiscoverBook flow (pick + fetch) on every filter tweak.
    """
    filters = _build_filter_clauses(
        genre_slugs, book_length, quality, moods, era, series_filter, popularity
    )
    return max(await _cached_matching_count(session, filters) - len(exclude_ids), 0)


class _Filters(typing.NamedTuple):
    where: typing.List[str]
    params: typing.Dict[str, typing.Any]
    needs_shelf_counts: bool

    @property
    def from_clause(self) -> str:
        return _DISCOVERY_FROM_WITH_SHELVES if self.needs_shelf_counts else _DISCOVERY_FROM

    def signature(self) -> str:
        payload = json.dumps([self.where, self.params], sort_keys=True, default=str)
        return hashlib.sha1(payload.encode()).hexdigest()[:20]


def _build_filter_clauses(
    genre_slugs: typing.List[str],
    book_length: str,
    quality: str,
    moods: typing.List[str],
    era: str,
    series_filter: str,
    popularity: str,
) -> _Filters:
    where: typing.List[str] = ["b.primary_cover_url IS NOT NULL AND b.primary_cover_url != ''"]
    params: typing.Dict[str, typing.Any] = {}
    needs_shelf_counts = False

    if book_length and book_length in BOOK_LENGTH_FILTERS:
        where.append(BOOK_LENGTH_FILTERS[book_length])

    if era and era in ERA_FILTERS:
        where.append(ERA_FILTERS[era])

    if series_filter == "standalone":
        where.append("b.series_id IS NULL")
    elif series_filter == "series":
        where.append("b.series_id IS NOT NULL")

    if genre_slugs:
        where.append(
            "EXISTS ("
            "SELECT 1 FROM books.book_genres bg2"
            " JOIN books.genres g2 ON bg2.genre_id = g2.genre_id"
            " WHERE bg2.book_id = b.book_id AND g2.slug = ANY(:genre_slugs)"
            ")"
        )
        params["genre_slugs"] = genre_slugs

    quality_bounds = {
        "high": f"{_COMBINED_RATING_EXPR} > 4.0",
        "medium": f"{_COMBINED_RATING_EXPR} > 3.0 AND {_COMBINED_RATING_EXPR} <= 4.0",
        "low": f"{_COMBINED_RATING_EXPR} > 2.0 AND {_COMBINED_RATING_EXPR} <= 3.0",
        "very_low": f"{_COMBINED_RATING_EXPR} <= 2.0",
    }
    if quality in quality_bounds:
        where.append("(b.rating_count + b.ol_rating_count) > 0")
        where.append(quality_bounds[quality])

    for mood in moods:
        jsonb_key = MOOD_TO_JSONB_KEY.get(mood)
        if jsonb_key:
            param_threshold = f"mood_threshold_{jsonb_key}"
            param_min_count = f"mood_min_count_{jsonb_key}"
            where.append(
                f"(b.sub_rating_stats->'{jsonb_key}'->>'avg')::numeric >= :{param_threshold}"
                f" AND (b.sub_rating_stats->'{jsonb_key}'->>'count')::int >= :{param_min_count}"
            )
            params[param_threshold] = MOOD_RATING_THRESHOLD
            params[param_min_count] = MOOD_MIN_RATING_COUNT

    if popularity == "popular":
        needs_shelf_counts = True
        where.append(f"{_TOTAL_READERS_EXPR} > :popular_threshold")
        params["popular_threshold"] = POPULAR_READER_THRESHOLD
    elif popularity == "hidden_gem":
        needs_shelf_counts = True
        where.append("(b.rating_count + b.ol_rating_count) > 0")
        where.append(f"{_TOTAL_READERS_EXPR} < :gem_max_readers")
        where.append(f"{_COMBINED_RATING_EXPR} > :gem_min_rating")
        params["gem_max_readers"] = HIDDEN_GEM_MAX_READERS
        params["gem_min_rating"] = HIDDEN_GEM_MIN_RATING

    return _Filters(where, params, needs_shelf_counts)


async def _id_bounds(session: sqlalchemy.ext.asyncio.AsyncSession) -> typing.Tuple[int, int]:
    """Lowest and highest book_id, cached briefly: the random pick starts anywhere in between."""
    now = time.monotonic()
    if now >= _bounds_cache["expires"]:
        row = (await session.execute(sqlalchemy.text("SELECT MIN(book_id) AS low, MAX(book_id) AS high FROM books.books"))).first()
        _bounds_cache.update(expires=now + BOUNDS_CACHE_TTL_SECONDS, low=row.low or 1, high=row.high or 1)
    return _bounds_cache["low"], _bounds_cache["high"]


async def _cached_matching_count(
    session: sqlalchemy.ext.asyncio.AsyncSession, filters: _Filters
) -> int:
    """Distinct works matching the filters. Counting walks the whole filtered set, so
    a count is reused for ten minutes instead of being recomputed on every click."""
    cache_key = f"discover:count:{filters.signature()}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return int(cached)

    query = (
        f"SELECT COUNT(*) FROM (SELECT 1 {filters.from_clause}"
        f" WHERE {' AND '.join(filters.where)} GROUP BY b.work_id) works"
    )
    count = (await session.execute(sqlalchemy.text(query), filters.params)).scalar() or 0
    await app.cache.set_cached(cache_key, count, COUNT_CACHE_TTL_SECONDS)
    return count


def _pick_query(filters: _Filters, language_filter: str) -> str:
    """First matching book at or after a random id, wrapping to the start when there is none.

    Walking the primary key from a random point costs about one row per 1/selectivity
    of the filter, instead of sorting the whole filtered set by RANDOM(). The second
    branch only runs when the first finds nothing, so an empty result is a true
    "no match", not an unlucky starting point.
    """
    conditions = " AND ".join([*filters.where, "b.book_id != ALL(:exclude_ids)", *([language_filter] if language_filter else [])])
    branch = (
        f"(SELECT b.book_id {filters.from_clause} WHERE b.book_id {{comparison}} :probe AND {conditions}"
        " ORDER BY b.book_id LIMIT 1)"
    )
    return f"{branch.format(comparison='>=')} UNION ALL {branch.format(comparison='<')} LIMIT 1"


def _exact_pick_query(filters: _Filters) -> str:
    conditions = " AND ".join([*filters.where, "b.book_id != ALL(:exclude_ids)"])
    return (
        f"SELECT b.book_id {filters.from_clause} WHERE {conditions}"
        " ORDER BY (b.language = :language) DESC, RANDOM() LIMIT 1"
    )


async def _pick_random_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    filters: _Filters,
    language: str,
    exclude_ids: typing.List[int],
    matching_count: int,
) -> typing.Optional[int]:
    """A random matching book, in the reader's language when one matches, else any language."""
    params = {**filters.params, "exclude_ids": exclude_ids or [0], "language": language}
    if matching_count < PROBE_MIN_MATCHES:
        row = (await session.execute(sqlalchemy.text(_exact_pick_query(filters)), params)).first()
        return row.book_id if row else None

    low, high = await _id_bounds(session)
    params["probe"] = random.randint(low, high)
    for language_filter in ("b.language = :language", ""):
        row = (await session.execute(sqlalchemy.text(_pick_query(filters, language_filter)), params)).first()
        if row is not None:
            return row.book_id
    return None


async def _fetch_book_summary_by_id(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    result = await session.execute(sqlalchemy.text(_BOOK_SUMMARY_SELECT), {"book_id": book_id})
    row = result.first()
    if row is None:
        return None
    return _row_to_discover_item(row)


def _row_to_discover_item(row: typing.Any) -> typing.Dict[str, typing.Any]:
    authors_list = app.services._row_helpers.json_agg_list(row.authors)

    return {
        "book_id": row.book_id,
        "title": row.title,
        "slug": row.slug,
        "description": row.description or "",
        "primary_cover_url": row.primary_cover_url or "",
        "rating_count": row.rating_count or 0,
        "avg_rating": str(row.avg_rating) if row.avg_rating else "0.00",
        "ol_rating_count": row.ol_rating_count or 0,
        "ol_avg_rating": str(row.ol_avg_rating) if row.ol_avg_rating else "0.00",
        "ol_want_to_read_count": row.ol_want_to_read_count or 0,
        "ol_currently_reading_count": row.ol_currently_reading_count or 0,
        "ol_already_read_count": row.ol_already_read_count or 0,
        "app_want_to_read_count": (
            int(row.app_want_to_read_count) if row.app_want_to_read_count else 0
        ),
        "app_reading_count": int(row.app_reading_count) if row.app_reading_count else 0,
        "app_read_count": int(row.app_read_count) if row.app_read_count else 0,
        "authors": authors_list,
    }


