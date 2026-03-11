import logging
import typing

import app.cache
import app.config
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_BOOK_FIELDS = """
    b.book_id,
    b.title,
    b.slug,
    b.language,
    b.primary_cover_url,
    COALESCE(b.avg_rating::text, '') AS avg_rating,
    b.rating_count,
    ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names,
    ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) AS author_slugs,
    COALESCE(b.ol_want_to_read_count, 0) + COALESCE(b.ol_currently_reading_count, 0) + COALESCE(b.ol_already_read_count, 0)
        + COALESCE((SELECT COUNT(*) FROM user_data.bookshelves bs_r
                     WHERE bs_r.book_id = b.book_id
                     AND bs_r.status IN ('want_to_read', 'reading', 'read')), 0) AS readers
"""

_BOOK_JOINS = """
    LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
    LEFT JOIN books.authors a ON ba.author_id = a.author_id
"""

_BOOK_BASE_WHERE = "b.primary_cover_url IS NOT NULL AND b.language = 'en'"

_BOOK_GROUP_BY = "GROUP BY b.book_id"


def _row_to_book_item(row: typing.Any, score: float) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": row.book_id,
        "title": row.title or "",
        "slug": row.slug or "",
        "language": row.language or "",
        "primary_cover_url": row.primary_cover_url or "",
        "avg_rating": row.avg_rating or "",
        "rating_count": row.rating_count or 0,
        "author_names": list(row.author_names or []),
        "author_slugs": list(row.author_slugs or []),
        "readers": int(row.readers or 0),
        "score": score,
    }


async def _build_most_read(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.ol_already_read_count AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.ol_already_read_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_wanted(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.ol_want_to_read_count AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.ol_want_to_read_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_trending_reads(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.ol_currently_reading_count AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.ol_currently_reading_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_viewed(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.view_count AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.view_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_highest_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.avg_rating AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE} AND b.rating_count >= 3
        {_BOOK_GROUP_BY}
        ORDER BY b.avg_rating DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_community_top_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
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
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.rating_count AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.rating_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_recently_added(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
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
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_classics(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, b.ol_already_read_count AS score
        FROM books.books b {_BOOK_JOINS}
        WHERE {_BOOK_BASE_WHERE}
          AND b.original_publication_year < 1980
          AND (b.ol_already_read_count >= 100 OR b.avg_rating >= 4.0)
        {_BOOK_GROUP_BY}
        ORDER BY b.ol_already_read_count DESC NULLS LAST, b.avg_rating DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_user_favorites(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, COUNT(*) AS score
        FROM user_data.bookshelves bs
        JOIN books.books b ON bs.book_id = b.book_id
        {_BOOK_JOINS}
        WHERE bs.is_favorite = true AND {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY COUNT(*) DESC
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_recently_finished(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT DISTINCT ON (b.book_id) {_BOOK_FIELDS}, EXTRACT(EPOCH FROM MAX(bs.updated_at)) AS score
        FROM user_data.bookshelves bs
        JOIN books.books b ON bs.book_id = b.book_id
        {_BOOK_JOINS}
        WHERE bs.status = 'read' AND {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY b.book_id, MAX(bs.updated_at) DESC
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_currently_reading(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        SELECT {_BOOK_FIELDS}, COUNT(*) AS score
        FROM user_data.bookshelves bs
        JOIN books.books b ON bs.book_id = b.book_id
        {_BOOK_JOINS}
        WHERE bs.status = 'reading' AND {_BOOK_BASE_WHERE}
        {_BOOK_GROUP_BY}
        ORDER BY COUNT(*) DESC
        LIMIT :limit
    """
        ),
        {"limit": limit},
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
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("writing_quality")), {"limit": limit}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_emotional(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("emotional_impact")), {"limit": limit}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_funniest(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("humor")), {"limit": limit}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_thought_provoking(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("intellectual_depth")), {"limit": limit}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_most_rereadable(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(_build_sub_rating_query("rereadability")), {"limit": limit}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


async def _build_top_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            """
        SELECT
            a.author_id,
            a.name,
            a.slug,
            COALESCE(a.photo_url, '') AS photo_url,
            COUNT(DISTINCT b.book_id) FILTER (WHERE b.language = 'en') AS book_count,
            SUM(b.avg_rating * b.rating_count) FILTER (WHERE b.language = 'en')
                / NULLIF(SUM(b.rating_count) FILTER (WHERE b.language = 'en'), 0) AS avg_rating,
            COALESCE(SUM(
                COALESCE(b.ol_want_to_read_count, 0) +
                COALESCE(b.ol_currently_reading_count, 0) +
                COALESCE(b.ol_already_read_count, 0)
            ) FILTER (WHERE b.language = 'en'), 0) + COALESCE((
                SELECT COUNT(*)
                FROM user_data.bookshelves bs_a
                JOIN books.book_authors ba3 ON bs_a.book_id = ba3.book_id
                JOIN books.books b3 ON ba3.book_id = b3.book_id
                WHERE ba3.author_id = a.author_id
                  AND b3.language = 'en'
                  AND bs_a.status IN ('want_to_read', 'reading', 'read')
            ), 0) AS readers,
            COALESCE(SUM(b.rating_count) FILTER (WHERE b.language = 'en'), 0) AS rating_count,
            COALESCE(SUM(b.ol_already_read_count) FILTER (WHERE b.language = 'en'), 0) AS score
        FROM books.authors a
        JOIN books.book_authors ba ON a.author_id = ba.author_id
        JOIN books.books b ON ba.book_id = b.book_id
        GROUP BY a.author_id
        ORDER BY score DESC
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [
        {
            "author_id": row.author_id,
            "name": row.name or "",
            "slug": row.slug or "",
            "photo_url": row.photo_url or "",
            "book_count": int(row.book_count or 0),
            "avg_rating": str(row.avg_rating) if row.avg_rating else "",
            "rating_count": int(row.rating_count or 0),
            "readers": int(row.readers or 0),
            "score": float(row.score or 0),
        }
        for row in result
    ]


async def _build_popular_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            """
        SELECT
            a.author_id,
            a.name,
            a.slug,
            COALESCE(a.photo_url, '') AS photo_url,
            COUNT(DISTINCT b.book_id) FILTER (WHERE b.language = 'en') AS book_count,
            SUM(b.avg_rating * b.rating_count) FILTER (WHERE b.language = 'en')
                / NULLIF(SUM(b.rating_count) FILTER (WHERE b.language = 'en'), 0) AS avg_rating,
            COALESCE(SUM(
                COALESCE(b.ol_want_to_read_count, 0) +
                COALESCE(b.ol_currently_reading_count, 0) +
                COALESCE(b.ol_already_read_count, 0)
            ) FILTER (WHERE b.language = 'en'), 0) + COALESCE((
                SELECT COUNT(*)
                FROM user_data.bookshelves bs_a
                JOIN books.book_authors ba3 ON bs_a.book_id = ba3.book_id
                JOIN books.books b3 ON ba3.book_id = b3.book_id
                WHERE ba3.author_id = a.author_id
                  AND b3.language = 'en'
                  AND bs_a.status IN ('want_to_read', 'reading', 'read')
            ), 0) AS readers,
            COALESCE(SUM(b.rating_count) FILTER (WHERE b.language = 'en'), 0) AS rating_count,
            COALESCE(a.view_count, 0) AS score
        FROM books.authors a
        LEFT JOIN books.book_authors ba ON a.author_id = ba.author_id
        LEFT JOIN books.books b ON ba.book_id = b.book_id
        GROUP BY a.author_id
        ORDER BY a.view_count DESC NULLS LAST
        LIMIT :limit
    """
        ),
        {"limit": limit},
    )
    return [
        {
            "author_id": row.author_id,
            "name": row.name or "",
            "slug": row.slug or "",
            "photo_url": row.photo_url or "",
            "book_count": int(row.book_count or 0),
            "avg_rating": str(row.avg_rating) if row.avg_rating else "",
            "rating_count": int(row.rating_count or 0),
            "readers": int(row.readers or 0),
            "score": float(row.score or 0),
        }
        for row in result
    ]


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


async def refresh_all(session_maker: sqlalchemy.orm.sessionmaker) -> None:
    settings = app.config.settings
    logger.info("[rec] Starting recommendation list refresh")

    for category in CATEGORIES:
        key = category["key"]
        item_type = category["item_type"]
        try:
            async with session_maker() as session:
                items = await category["build_fn"](session, settings.list_default_size)
            items_key = "book_items" if item_type == "book" else "author_items"
            payload = {
                "category": key,
                "display_name": category["display_name"],
                "item_type": item_type,
                items_key: items,
                "total": len(items),
            }
            await app.cache.set_cached(
                f"rec:{key}", payload, settings.cache_recommendation_ttl
            )
            logger.info(f"[rec] Cached {len(items)} items for category '{key}'")
        except Exception as e:
            logger.error(f"[rec] Failed to build category '{key}': {str(e)}")

    logger.info("[rec] Recommendation list refresh complete")
