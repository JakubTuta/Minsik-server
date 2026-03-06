import logging
import typing

import app.cache
import app.config
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.orm
from sqlalchemy import text

logger = logging.getLogger(__name__)

RARITY_TIERS: typing.List[typing.Tuple[str, float, float, float]] = [
    ("legendary", 4.75, 5.01, 0.015),
    ("ultra_rare", 4.50, 4.75, 0.035),
    ("super_rare", 4.00, 4.50, 0.10),
    ("rare", 3.25, 4.00, 0.20),
    ("uncommon", 2.25, 3.25, 0.30),
    ("common", 0.00, 2.25, 0.35),
]

RARITY_MIN_RATINGS: typing.Dict[str, int] = {
    "legendary": 50,
    "ultra_rare": 30,
    "super_rare": 15,
    "rare": 8,
    "uncommon": 3,
    "common": 1,
}

POOL_SIZES: typing.Dict[str, int] = {
    "legendary": 20,
    "ultra_rare": 30,
    "super_rare": 40,
    "rare": 60,
    "uncommon": 80,
    "common": 100,
}

CACHE_KEY_PREFIX = "case:pool"
LANGUAGE = "en"

_POOL_QUERY = text(
    """
    WITH book_stats AS (
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
            (
                COALESCE(b.avg_rating::numeric, 0) * b.rating_count
                + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
            )::numeric / (b.rating_count + b.ol_rating_count) AS combined_rating,
            b.rating_count + b.ol_rating_count AS total_ratings,
            COALESCE(bs.app_want_to_read_count, 0) AS app_want_to_read_count,
            COALESCE(bs.app_reading_count, 0)      AS app_reading_count,
            COALESCE(bs.app_read_count, 0)         AS app_read_count,
            ARRAY_AGG(a.author_id) FILTER (WHERE a.author_id IS NOT NULL) AS author_ids,
            ARRAY_AGG(a.name)      FILTER (WHERE a.name IS NOT NULL)      AS author_names,
            ARRAY_AGG(a.slug)      FILTER (WHERE a.slug IS NOT NULL)      AS author_slugs,
            ARRAY_AGG(a.photo_url) FILTER (WHERE a.photo_url IS NOT NULL) AS author_photos
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN (
            SELECT
                book_id,
                COUNT(*) FILTER (WHERE status = 'want_to_read') AS app_want_to_read_count,
                COUNT(*) FILTER (WHERE status = 'reading')      AS app_reading_count,
                COUNT(*) FILTER (WHERE status = 'read')         AS app_read_count
            FROM user_data.bookshelves
            WHERE status != 'abandoned'
            GROUP BY book_id
        ) bs ON b.book_id = bs.book_id
        WHERE b.language = 'en'
          AND (b.rating_count + b.ol_rating_count) >= 1
        GROUP BY b.book_id, b.title, b.slug, b.description, b.primary_cover_url,
                 b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
                 b.ol_want_to_read_count, b.ol_currently_reading_count,
                 b.ol_already_read_count, bs.app_want_to_read_count,
                 bs.app_reading_count, bs.app_read_count
    ),
    bucketed AS (
        SELECT *,
            CASE
                WHEN total_ratings >= 50 AND combined_rating >  4.75                              THEN 'legendary'
                WHEN total_ratings >= 30 AND combined_rating >  4.50 AND combined_rating <= 4.75  THEN 'ultra_rare'
                WHEN total_ratings >= 15 AND combined_rating >  4.00 AND combined_rating <= 4.50  THEN 'super_rare'
                WHEN total_ratings >=  8 AND combined_rating >  3.25 AND combined_rating <= 4.00  THEN 'rare'
                WHEN total_ratings >=  3 AND combined_rating >  2.25 AND combined_rating <= 3.25  THEN 'uncommon'
                WHEN total_ratings >=  1 AND combined_rating <= 2.25                              THEN 'common'
                ELSE NULL
            END AS rarity_name
        FROM book_stats
    ),
    sampled AS (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY rarity_name ORDER BY RANDOM()) AS rn
        FROM bucketed
        WHERE rarity_name IS NOT NULL
    )
    SELECT * FROM sampled
    WHERE (rarity_name = 'legendary'  AND rn <= 20)
       OR (rarity_name = 'ultra_rare' AND rn <= 30)
       OR (rarity_name = 'super_rare' AND rn <= 40)
       OR (rarity_name = 'rare'       AND rn <= 60)
       OR (rarity_name = 'uncommon'   AND rn <= 80)
       OR (rarity_name = 'common'     AND rn <= 100)
    """
)


def _row_to_pool_item(row: typing.Any) -> typing.Dict[str, typing.Any]:
    author_ids = row.author_ids or []
    author_names = row.author_names or []
    author_slugs = row.author_slugs or []
    author_photos = row.author_photos or []

    authors = []
    for i, author_id in enumerate(author_ids):
        authors.append(
            {
                "author_id": author_id,
                "name": author_names[i] if i < len(author_names) else "",
                "slug": author_slugs[i] if i < len(author_slugs) else "",
                "photo_url": author_photos[i] if i < len(author_photos) else "",
            }
        )

    return {
        "book_id": row.book_id,
        "title": row.title,
        "slug": row.slug,
        "description": row.description or "",
        "primary_cover_url": row.primary_cover_url or "",
        "authors": authors,
        "rarity": row.rarity_name,
        "avg_rating": str(row.avg_rating) if row.avg_rating else "0.00",
        "rating_count": row.rating_count or 0,
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
    }


async def refresh_case_pools(session_maker: sqlalchemy.orm.sessionmaker) -> None:
    logger.info(f"[case] Starting case pool refresh for language '{LANGUAGE}'")
    settings = app.config.settings

    try:
        async with session_maker() as session:
            result = await session.execute(_POOL_QUERY)
            rows = result.fetchall()
    except Exception as e:
        logger.error(f"[case] Failed to fetch case pool books: {str(e)}")
        return

    pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {
        tier_name: [] for tier_name, *_ in RARITY_TIERS
    }
    for row in rows:
        pools[row.rarity_name].append(_row_to_pool_item(row))

    for tier_name, pool in pools.items():
        key = f"{CACHE_KEY_PREFIX}:{tier_name}:{LANGUAGE}"
        await app.cache.set_cached(key, pool, settings.cache_case_pool_ttl)
        logger.info(
            f"[case] Cached {len(pool)} books for tier '{tier_name}' (key: {key})"
        )

    logger.info("[case] Case pool refresh complete")
