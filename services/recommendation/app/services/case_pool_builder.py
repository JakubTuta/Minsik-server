import logging
import typing

import app.cache
import app.config
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.orm

logger = logging.getLogger(__name__)

RARITY_TIERS: typing.List[typing.Tuple[str, float, float, float]] = [
    ("legendary", 4.65, 5.01, 0.015),
    ("ultra_rare", 4.50, 4.65, 0.035),
    ("super_rare", 4.00, 4.50, 0.10),
    ("rare", 3.25, 4.00, 0.20),
    ("uncommon", 2.25, 3.25, 0.30),
    ("common", 0.00, 2.25, 0.35),
]

CACHE_KEY_PREFIX = "case:pool"

_POOL_QUERY = sqlalchemy.text(
    """
    -- Rarity only depends on combined_rating/total_ratings, both derived from
    -- books.books columns alone. The old version joined authors and carried
    -- description/cover text through the dedup and windowed-sample passes for
    -- every rated book (hundreds of thousands of rows) to keep ~440 rows at
    -- the end — three full sorts/aggregates of the whole catalog per refresh,
    -- heavy enough to crash Postgres under this container's memory limit.
    -- Picking survivors on the lean row first and joining authors only for
    -- those turns three catalog-wide passes into one, plus a join scoped to
    -- ~440 rows.
    WITH rated AS (
        SELECT
            b.book_id,
            b.work_id,
            (
                COALESCE(b.avg_rating::numeric, 0) * b.rating_count
                + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
            )::numeric / (b.rating_count + b.ol_rating_count) AS combined_rating,
            b.rating_count + b.ol_rating_count AS total_ratings
        FROM books.books b
        WHERE (b.rating_count + b.ol_rating_count) >= 1
    ),
    -- ol_* stats and pooled ratings are identical across a work's translations,
    -- so without this a heavily-translated work would occupy many pool slots
    -- for the same rarity tier, crowding out other distinct works. Tie-break
    -- is total_ratings only (no language bias) so the pool's language mix
    -- reflects real edition popularity, letting pick_weighted_from_pool's
    -- language boost actually surface non-English editions.
    work_deduped AS (
        SELECT DISTINCT ON (work_id) book_id, combined_rating, total_ratings
        FROM rated
        ORDER BY work_id, total_ratings DESC
    ),
    bucketed AS (
        SELECT book_id,
            CASE
                WHEN total_ratings >= 25 AND combined_rating >  4.65                              THEN 'legendary'
                WHEN total_ratings >= 20 AND combined_rating >  4.50 AND combined_rating <= 4.65  THEN 'ultra_rare'
                WHEN total_ratings >= 15 AND combined_rating >  4.00 AND combined_rating <= 4.50  THEN 'super_rare'
                WHEN total_ratings >=  8 AND combined_rating >  3.25 AND combined_rating <= 4.00  THEN 'rare'
                WHEN total_ratings >=  3 AND combined_rating >  2.25 AND combined_rating <= 3.25  THEN 'uncommon'
                WHEN total_ratings >=  1 AND combined_rating <= 2.25                              THEN 'common'
                ELSE NULL
            END AS rarity_name
        FROM work_deduped
    ),
    sampled AS (
        SELECT book_id, rarity_name,
            ROW_NUMBER() OVER (PARTITION BY rarity_name ORDER BY RANDOM()) AS rn
        FROM bucketed
        WHERE rarity_name IS NOT NULL
    ),
    picked AS (
        SELECT book_id, rarity_name FROM sampled
        WHERE (rarity_name = 'legendary'  AND rn <= 20)
           OR (rarity_name = 'ultra_rare' AND rn <= 30)
           OR (rarity_name = 'super_rare' AND rn <= 50)
           OR (rarity_name = 'rare'       AND rn <= 80)
           OR (rarity_name = 'uncommon'   AND rn <= 110)
           OR (rarity_name = 'common'     AND rn <= 150)
    )
    SELECT
        b.book_id,
        b.title,
        b.slug,
        b.work_id,
        b.description,
        b.primary_cover_url,
        b.language,
        b.rating_count,
        b.avg_rating,
        b.ol_rating_count,
        b.ol_avg_rating,
        b.ol_want_to_read_count,
        b.ol_currently_reading_count,
        b.ol_already_read_count,
        COALESCE(wsc.want_to_read_count, 0) AS app_want_to_read_count,
        COALESCE(wsc.reading_count, 0)      AS app_reading_count,
        COALESCE(wsc.read_count, 0)         AS app_read_count,
        p.rarity_name,
        ARRAY_AGG(a.author_id) FILTER (WHERE a.author_id IS NOT NULL) AS author_ids,
        ARRAY_AGG(a.name)      FILTER (WHERE a.name IS NOT NULL)      AS author_names,
        ARRAY_AGG(a.slug)      FILTER (WHERE a.slug IS NOT NULL)      AS author_slugs,
        ARRAY_AGG(a.photo_url) FILTER (WHERE a.photo_url IS NOT NULL) AS author_photos
    FROM picked p
    JOIN books.books b ON b.book_id = p.book_id
    LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
    LEFT JOIN books.authors a ON ba.author_id = a.author_id
    LEFT JOIN books.work_shelf_counts wsc ON wsc.work_id = b.work_id
    GROUP BY b.book_id, b.title, b.slug, b.work_id, b.description, b.primary_cover_url,
             b.language, b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
             b.ol_want_to_read_count, b.ol_currently_reading_count,
             b.ol_already_read_count, wsc.want_to_read_count,
             wsc.reading_count, wsc.read_count, p.rarity_name
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
        "work_id": row.work_id,
        "title": row.title,
        "slug": row.slug,
        "description": row.description or "",
        "primary_cover_url": row.primary_cover_url or "",
        "language": row.language or "",
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
    logger.info("[case] Starting case pool refresh (global, all languages)")
    settings = app.config.settings

    try:
        async with session_maker() as session:
            result = await session.execute(_POOL_QUERY)
            rows = result.fetchall()
    except Exception:
        logger.exception("[case] Failed to fetch case pool books")
        return

    pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {
        tier_name: [] for tier_name, *_ in RARITY_TIERS
    }
    for row in rows:
        pools[row.rarity_name].append(_row_to_pool_item(row))

    for tier_name, pool in pools.items():
        key = f"{CACHE_KEY_PREFIX}:{tier_name}"
        await app.cache.set_cached(key, pool, settings.cache_case_pool_ttl)
        logger.info(
            f"[case] Cached {len(pool)} books for tier '{tier_name}' (key: {key})"
        )

    logger.info("[case] Case pool refresh complete")
