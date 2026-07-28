import asyncio
import logging
import typing

import app.cache
import app.config
import app.services._language_boost
import app.services.author_recommender
import app.services.book_of_week_builder
import app.services.book_recommender
import app.services.series_recommender
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

# Shelf counts are pooled per work and counted per distinct user, so a book's
# popularity is the same in every language and a reader who shelved two
# translations still counts once. ol_* counts are already work-level: the dump
# pipeline writes them identically to every language row.
_READERS_EXPR = """
    COALESCE(b.ol_want_to_read_count, 0) + COALESCE(b.ol_currently_reading_count, 0)
    + COALESCE(b.ol_already_read_count, 0) + COALESCE(MAX(bs_agg.app_readers), 0)
"""

_WANT_TO_READ_EXPR = (
    "COALESCE(b.ol_want_to_read_count, 0) + COALESCE(MAX(bs_agg.app_want_to_read), 0)"
)

_CURRENTLY_READING_EXPR = (
    "COALESCE(b.ol_currently_reading_count, 0) + COALESCE(MAX(bs_agg.app_reading), 0)"
)

_RATING_COUNT_EXPR = "COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)"

_BOOK_FIELDS = f"""
    b.book_id,
    b.title,
    b.slug,
    b.work_id,
    b.language,
    b.primary_cover_url,
    CASE
        WHEN ({_RATING_COUNT_EXPR}) > 0
        THEN ROUND(
            (COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
             + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0))
            / ({_RATING_COUNT_EXPR}), 2
        )::text
        ELSE ''
    END AS avg_rating,
    {_RATING_COUNT_EXPR} AS rating_count,
    ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names,
    ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) AS author_slugs,
    {_READERS_EXPR} AS readers
"""

_BOOK_JOINS = """
    LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
    LEFT JOIN books.authors a ON ba.author_id = a.author_id
    LEFT JOIN LATERAL (
        SELECT
            COUNT(DISTINCT bs_r.user_id) AS app_readers,
            COUNT(DISTINCT bs_r.user_id) FILTER (WHERE bs_r.status = 'want_to_read')
                AS app_want_to_read,
            COUNT(DISTINCT bs_r.user_id) FILTER (WHERE bs_r.status = 'reading')
                AS app_reading
        FROM user_data.bookshelves bs_r
        JOIN books.books rb ON rb.book_id = bs_r.book_id
        WHERE rb.work_id = b.work_id
    ) bs_agg ON TRUE
"""

_BOOK_BASE_WHERE = (
    "b.primary_cover_url IS NOT NULL AND "
    + app.services._language_boost.preferred_edition_sql()
)

_BOOK_GROUP_BY = "GROUP BY b.book_id"

# One row per (author, work): picks the edition with the most ratings so an
# author's translated catalog isn't summed/counted once per language.
_AUTHOR_WORKS_CTE = """
        author_works AS (
            SELECT DISTINCT ON (ba.author_id, b.work_id)
                ba.author_id,
                b.book_id,
                b.rating_count,
                b.ol_rating_count,
                b.avg_rating,
                b.ol_avg_rating,
                b.ol_want_to_read_count,
                b.ol_currently_reading_count,
                b.ol_already_read_count
            FROM books.book_authors ba
            JOIN books.books b ON ba.book_id = b.book_id
            ORDER BY ba.author_id, b.work_id,
                     (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) DESC
        )
"""


def _row_to_book_item(row: typing.Any, score: float) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": row.book_id,
        "title": row.title or "",
        "slug": row.slug or "",
        "work_id": row.work_id or "",
        "language": row.language or "",
        "primary_cover_url": row.primary_cover_url or "",
        "avg_rating": row.avg_rating or "",
        "rating_count": row.rating_count or 0,
        "author_names": list(row.author_names or []),
        "author_slugs": list(row.author_slugs or []),
        "readers": int(row.readers or 0),
        "score": score,
    }


def _row_to_author_item(row: typing.Any, score: float) -> typing.Dict[str, typing.Any]:
    return {
        "author_id": row.author_id,
        "name": row.name or "",
        "slug": row.slug or "",
        "photo_url": row.photo_url or "",
        "book_count": int(row.book_count or 0),
        "avg_rating": str(row.avg_rating) if row.avg_rating else "",
        "rating_count": int(row.rating_count or 0),
        "readers": int(row.readers or 0),
        "score": score,
    }


def _make_book_section(
    section_key: str,
    display_name: str,
    items: typing.List[typing.Dict[str, typing.Any]],
    title_params: typing.Optional[typing.Dict[str, str]] = None,
) -> typing.Dict[str, typing.Any]:
    return {
        "section_key": section_key,
        "display_name": display_name,
        "item_type": "book",
        "book_items": items,
        "total": len(items),
        "title_params": title_params or {},
    }


async def _build_most_read(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, {_READERS_EXPR} AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_wanted(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, {_WANT_TO_READ_EXPR} AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_trending_reads(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, {_CURRENTLY_READING_EXPR} AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_viewed(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS},
               {app.services._language_boost.work_view_count_sql()} AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_highest_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS},
               CASE
                   WHEN (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) = 0 THEN 0
                   ELSE (
                       COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
                       + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0)
                   ) / (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0))
               END AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
          AND (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) >= 3
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_community_top_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.ol_avg_rating AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE} AND b.ol_rating_count >= 20
        {_BOOK_GROUP_BY}
        ORDER BY b.ol_avg_rating DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS},
               COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_recently_added(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, EXTRACT(EPOCH FROM b.created_at) AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.created_at DESC
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_classics(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, {_READERS_EXPR} AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
          AND b.original_publication_year < 1980
        {_BOOK_GROUP_BY}
        HAVING ({_READERS_EXPR}) >= 100 OR b.avg_rating >= 4.0
        ORDER BY score DESC NULLS LAST, b.avg_rating DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_user_favorites(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, COUNT(DISTINCT bs.user_id) AS score
        FROM books.books b
        JOIN books.books wb ON wb.work_id = b.work_id
        JOIN user_data.bookshelves bs ON bs.book_id = wb.book_id
        {_BOOK_JOINS}
        WHERE bs.is_favorite = true AND {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_recently_finished(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, EXTRACT(EPOCH FROM MAX(bs.updated_at)) AS score
        FROM books.books b
        JOIN books.books wb ON wb.work_id = b.work_id
        JOIN user_data.bookshelves bs ON bs.book_id = wb.book_id
        {_BOOK_JOINS}
        WHERE bs.status = 'read' AND {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY MAX(bs.updated_at) DESC
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_currently_reading(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, COUNT(DISTINCT bs.user_id) AS score
        FROM books.books b
        JOIN books.books wb ON wb.work_id = b.work_id
        JOIN user_data.bookshelves bs ON bs.book_id = wb.book_id
        {_BOOK_JOINS}
        WHERE bs.status = 'reading' AND {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY score DESC
        LIMIT :limit
    """
        ),
        {"limit": limit, "language": language},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


def _build_sub_rating_query(dimension: str) -> str:
    return f"""
        SELECT {_BOOK_FIELDS},
               CAST(b.sub_rating_stats->'{dimension}'->>'avg' AS FLOAT) AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
          AND b.sub_rating_stats->'{dimension}'->>'count' IS NOT NULL
          AND CAST(b.sub_rating_stats->'{dimension}'->>'count' AS INTEGER) >= 3
        {_BOOK_GROUP_BY}
        ORDER BY score DESC NULLS LAST
        LIMIT :limit
    """


async def _build_best_writing(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("writing_quality")), {"limit": limit, "language": language}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_emotional(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("emotional_impact")), {"limit": limit, "language": language}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_funniest(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("humor")), {"limit": limit, "language": language}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_thought_provoking(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("intellectual_depth")), {"limit": limit, "language": language}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_rereadable(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("rereadability")), {"limit": limit, "language": language}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_top_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        WITH author_app_readers AS (
            SELECT ba_r.author_id, COUNT(DISTINCT bs_a.user_id) AS app_readers
            FROM user_data.bookshelves bs_a
            JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
            GROUP BY ba_r.author_id
        ),
        {_AUTHOR_WORKS_CTE}
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
            COALESCE(SUM(
                COALESCE(aw.ol_want_to_read_count, 0) +
                COALESCE(aw.ol_currently_reading_count, 0) +
                COALESCE(aw.ol_already_read_count, 0)
            ), 0) + COALESCE(aar.app_readers, 0) AS readers,
            COALESCE(SUM(aw.rating_count + aw.ol_rating_count), 0) AS rating_count,
            COALESCE(SUM(
                COALESCE(aw.ol_want_to_read_count, 0) +
                COALESCE(aw.ol_currently_reading_count, 0) +
                COALESCE(aw.ol_already_read_count, 0)
            ), 0) + COALESCE(aar.app_readers, 0) AS score
        FROM books.authors a
        JOIN author_works aw ON aw.author_id = a.author_id
        LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
        GROUP BY a.author_id, aar.app_readers
        ORDER BY score DESC
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_author_item(row, float(row.score or 0)) for row in result]


async def _build_popular_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        WITH author_app_readers AS (
            SELECT ba_r.author_id, COUNT(DISTINCT bs_a.user_id) AS app_readers
            FROM user_data.bookshelves bs_a
            JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
            GROUP BY ba_r.author_id
        ),
        {_AUTHOR_WORKS_CTE}
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
            COALESCE(SUM(
                COALESCE(aw.ol_want_to_read_count, 0) +
                COALESCE(aw.ol_currently_reading_count, 0) +
                COALESCE(aw.ol_already_read_count, 0)
            ), 0) + COALESCE(aar.app_readers, 0) AS readers,
            COALESCE(SUM(aw.rating_count + aw.ol_rating_count), 0) AS rating_count,
            COALESCE(a.view_count, 0) AS score
        FROM books.authors a
        LEFT JOIN author_works aw ON aw.author_id = a.author_id
        LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
        GROUP BY a.author_id, aar.app_readers
        ORDER BY a.view_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_author_item(row, float(row.score or 0)) for row in result]


CATEGORIES: typing.List[typing.Dict[str, typing.Any]] = [
    {
        "key": "most_read",
        "display_name": "Most Read Books",
        "item_type": "book",
        "build_fn": _build_most_read,
    },
    {
        "key": "most_wanted",
        "display_name": "Most Wanted Books",
        "item_type": "book",
        "build_fn": _build_most_wanted,
    },
    {
        "key": "trending_reads",
        "display_name": "Trending Right Now",
        "item_type": "book",
        "build_fn": _build_trending_reads,
    },
    {
        "key": "most_viewed",
        "display_name": "Most Popular",
        "item_type": "book",
        "build_fn": _build_most_viewed,
    },
    {
        "key": "highest_rated",
        "display_name": "Highest Rated",
        "item_type": "book",
        "build_fn": _build_highest_rated,
    },
    {
        "key": "community_top_rated",
        "display_name": "Community Favorites",
        "item_type": "book",
        "build_fn": _build_community_top_rated,
    },
    {
        "key": "most_rated",
        "display_name": "Most Reviewed",
        "item_type": "book",
        "build_fn": _build_most_rated,
    },
    {
        "key": "recently_added",
        "display_name": "Recently Added",
        "item_type": "book",
        "build_fn": _build_recently_added,
    },
    {
        "key": "classics",
        "display_name": "Classic Books",
        "item_type": "book",
        "build_fn": _build_classics,
    },
    {
        "key": "user_favorites",
        "display_name": "User Favorites",
        "item_type": "book",
        "build_fn": _build_user_favorites,
    },
    {
        "key": "recently_finished",
        "display_name": "Recently Finished",
        "item_type": "book",
        "build_fn": _build_recently_finished,
    },
    {
        "key": "currently_reading",
        "display_name": "Currently Being Read",
        "item_type": "book",
        "build_fn": _build_currently_reading,
    },
    {
        "key": "best_writing",
        "display_name": "Best Writing",
        "item_type": "book",
        "build_fn": _build_best_writing,
    },
    {
        "key": "most_emotional",
        "display_name": "Most Emotional",
        "item_type": "book",
        "build_fn": _build_most_emotional,
    },
    {
        "key": "funniest",
        "display_name": "Funniest Books",
        "item_type": "book",
        "build_fn": _build_funniest,
    },
    {
        "key": "most_thought_provoking",
        "display_name": "Most Thought-Provoking",
        "item_type": "book",
        "build_fn": _build_most_thought_provoking,
    },
    {
        "key": "most_rereadable",
        "display_name": "Most Rereadable",
        "item_type": "book",
        "build_fn": _build_most_rereadable,
    },
    {
        "key": "top_authors",
        "display_name": "Most Read Authors",
        "item_type": "author",
        "build_fn": _build_top_authors,
    },
    {
        "key": "popular_authors",
        "display_name": "Popular Authors",
        "item_type": "author",
        "build_fn": _build_popular_authors,
    },
]

CATEGORY_KEYS: typing.Set[str] = {c["key"] for c in CATEGORIES}
CATEGORY_ITEM_TYPES: typing.Dict[str, str] = {c["key"]: c["item_type"] for c in CATEGORIES}


def get_category_item_type(category: str) -> typing.Optional[str]:
    return CATEGORY_ITEM_TYPES.get(category)


async def _collect_series_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.Set[int],
) -> typing.Set[int]:
    if not book_ids:
        return set()
    result = await session.execute(
        sqlalchemy.text(
            "SELECT DISTINCT series_id FROM books.books "
            "WHERE book_id = ANY(:ids) AND series_id IS NOT NULL"
        ),
        {"ids": list(book_ids)},
    )
    return {row.series_id for row in result}


async def _precache_contextual(
    session_maker: typing.Any,
    ids: typing.Set[int],
    builder_fn: typing.Callable,
    key_prefix: str,
    ttl: int,
    limit: int,
) -> None:
    if not ids:
        return

    sem = asyncio.Semaphore(5)

    async def _one(eid: int) -> bool:
        async with sem:
            try:
                sections = await builder_fn(session_maker, eid, limit)
                if sections:
                    await app.cache.set_cached(f"{key_prefix}:{eid}", sections, ttl)
                    return True
            except Exception as e:
                logger.error(f"[rec] precache {key_prefix}:{eid} failed: {e}")
            return False

    results = await asyncio.gather(*(_one(i) for i in ids))
    logger.info(
        f"[rec] Precached {sum(results)}/{len(ids)} contextual recs for {key_prefix}"
    )


def recommendation_list_cache_key(category: str, item_type: str, language: str) -> str:
    if item_type == "author":
        return f"rec:{category}"
    return f"rec:{category}:{language}"


async def refresh_all(session_maker: sqlalchemy.orm.sessionmaker) -> None:
    settings = app.config.settings
    logger.info("[rec] Starting recommendation list refresh")

    languages = app.services.book_of_week_builder.available_languages()
    book_ids: typing.Set[int] = set()
    author_ids: typing.Set[int] = set()

    for category in CATEGORIES:
        key = category["key"]
        item_type = category["item_type"]
        build_languages = languages if item_type == "book" else [languages[0]]

        for language in build_languages:
            try:
                async with session_maker() as session:
                    if item_type == "book":
                        items = await category["build_fn"](
                            session, settings.list_default_size * 2, language
                        )
                    else:
                        items = await category["build_fn"](
                            session, settings.list_default_size * 2
                        )
                items_key = "book_items" if item_type == "book" else "author_items"
                payload = {
                    "category": key,
                    "display_name": category["display_name"],
                    "item_type": item_type,
                    items_key: items,
                    "total": len(items),
                }
                cache_key = recommendation_list_cache_key(key, item_type, language)
                await app.cache.set_cached(
                    cache_key, payload, settings.cache_recommendation_ttl
                )
                logger.info(f"[rec] Cached {len(items)} items for '{cache_key}'")
                if item_type == "book":
                    for item in items:
                        bid = item.get("book_id")
                        if bid:
                            book_ids.add(bid)
                elif item_type == "author":
                    for item in items:
                        aid = item.get("author_id")
                        if aid:
                            author_ids.add(aid)
            except Exception as e:
                logger.error(f"[rec] Failed to build category '{key}' ({language}): {str(e)}")

    logger.info("[rec] Recommendation list refresh complete")

    ttl = settings.cache_recommendation_ttl
    precache_limit = 10

    async with session_maker() as session:
        series_ids = await _collect_series_ids(session, book_ids)

    await _precache_contextual(
        session_maker,
        book_ids,
        app.services.book_recommender.build_book_recommendations,
        "rec:book",
        ttl,
        precache_limit,
    )
    await _precache_contextual(
        session_maker,
        author_ids,
        app.services.author_recommender.build_author_recommendations,
        "rec:author",
        ttl,
        precache_limit,
    )
    await _precache_contextual(
        session_maker,
        series_ids,
        app.services.series_recommender.build_series_recommendations,
        "rec:series",
        ttl,
        precache_limit,
    )
