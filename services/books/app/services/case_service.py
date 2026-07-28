import logging
import random
import typing

import app.cache
import app.services._language_boost
import sqlalchemy
import sqlalchemy.ext.asyncio

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
    "legendary": 30,
    "ultra_rare": 20,
    "super_rare": 15,
    "rare": 8,
    "uncommon": 3,
    "common": 1,
}

CACHE_POOL_KEY_PREFIX = "case:pool"

_BOOK_SELECT = """
    SELECT
        b.book_id,
        b.title,
        b.slug,
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
        (
            COALESCE(b.avg_rating::numeric, 0) * b.rating_count
            + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
        )::numeric / NULLIF(b.rating_count + b.ol_rating_count, 0) AS combined_rating,
        b.rating_count + b.ol_rating_count AS total_rating_count,
        b.ol_want_to_read_count + b.ol_currently_reading_count + b.ol_already_read_count
            + COALESCE(bs.app_want_to_read_count, 0)
            + COALESCE(bs.app_reading_count, 0)
            + COALESCE(bs.app_read_count, 0) AS total_readers,
        COALESCE(bs.app_want_to_read_count, 0) AS app_want_to_read_count,
        COALESCE(bs.app_reading_count, 0) AS app_reading_count,
        COALESCE(bs.app_read_count, 0) AS app_read_count,
        ARRAY_AGG(a.author_id) FILTER (WHERE a.author_id IS NOT NULL) AS author_ids,
        ARRAY_AGG(a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names,
        ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) AS author_slugs,
        ARRAY_AGG(a.photo_url) FILTER (WHERE a.photo_url IS NOT NULL) AS author_photos
    FROM books.books b
    LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
    LEFT JOIN books.authors a ON ba.author_id = a.author_id
    LEFT JOIN (
        SELECT
            wb.work_id,
            COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'want_to_read') AS app_want_to_read_count,
            COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'reading') AS app_reading_count,
            COUNT(DISTINCT bsh.user_id) FILTER (WHERE bsh.status = 'read') AS app_read_count
        FROM user_data.bookshelves bsh
        JOIN books.books wb ON wb.book_id = bsh.book_id
        WHERE bsh.status != 'abandoned'
        GROUP BY wb.work_id
    ) bs ON b.work_id = bs.work_id
"""

_BOOK_GROUP_BY = """
    GROUP BY b.book_id, b.title, b.slug, b.description, b.primary_cover_url,
             b.language, b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
             b.ol_want_to_read_count, b.ol_currently_reading_count,
             b.ol_already_read_count, bs.app_want_to_read_count,
             bs.app_reading_count, bs.app_read_count
"""

_COMBINED_RATING_FILTER = """
    (
        COALESCE(b.avg_rating::numeric, 0) * b.rating_count
        + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
    ) / NULLIF(b.rating_count + b.ol_rating_count, 0) > :min_rating
    AND (
        COALESCE(b.avg_rating::numeric, 0) * b.rating_count
        + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
    ) / NULLIF(b.rating_count + b.ol_rating_count, 0) <= :max_rating
"""


async def open_case(
    session: sqlalchemy.ext.asyncio.AsyncSession, language: str
) -> typing.Dict[str, typing.Any]:
    cached_result = await _try_open_from_cache(language)
    if cached_result is not None:
        return cached_result

    tier = pick_winning_tier()
    winner_row = await fetch_tier_row_with_fallback(session, language, tier)

    if winner_row is None:
        raise ValueError("No rated books found")

    winner_item = row_to_case_item(winner_row)

    return {
        "winner": winner_item,
    }


async def _try_open_from_cache(
    language: str,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    tier_pools = await load_cached_tier_pools()
    if tier_pools is None:
        return None

    winning_tier = pick_winning_tier()
    winner_pool = eligible_pool_books(tier_pools, winning_tier[0], frozenset())
    if not winner_pool:
        return None

    winner = pick_weighted_from_pool(winner_pool, language)
    if "rarity" not in winner:
        winner["rarity"] = winning_tier[0]

    return {
        "winner": winner,
    }


def pick_winning_tier() -> typing.Tuple[str, float, float, float]:
    roll = random.random()
    cumulative = 0.0
    for tier in RARITY_TIERS:
        cumulative += tier[3]
        if roll < cumulative:
            return tier
    return RARITY_TIERS[-1]


def tier_fallback_candidates(
    tier_name: str,
) -> typing.List[typing.Tuple[str, float, float, float]]:
    tier_index = next(
        (i for i, t in enumerate(RARITY_TIERS) if t[0] == tier_name), None
    )
    if tier_index is None:
        return []

    candidates: typing.List[typing.Tuple[str, float, float, float]] = []
    for i in range(1, len(RARITY_TIERS)):
        for idx in (tier_index + i, tier_index - i):
            if 0 <= idx < len(RARITY_TIERS):
                candidates.append(RARITY_TIERS[idx])
    return candidates


async def load_cached_tier_pools() -> typing.Optional[
    typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]]
]:
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {}
    for tier_name, _, _, _ in RARITY_TIERS:
        pool = await app.cache.get_cached(f"{CACHE_POOL_KEY_PREFIX}:{tier_name}")
        if pool is None:
            return None
        tier_pools[tier_name] = pool
    return tier_pools


def pick_weighted_from_pool(
    pool: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.Dict[str, typing.Any]:
    weights = [
        app.services._language_boost.lang_boost_weight(b.get("language", ""), language)
        for b in pool
    ]
    return random.choices(pool, weights=weights, k=1)[0]


def eligible_pool_books(
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]],
    tier_name: str,
    used_ids: typing.AbstractSet[int],
) -> typing.List[typing.Dict[str, typing.Any]]:
    pool = tier_pools.get(tier_name, [])
    eligible = [b for b in pool if b["book_id"] not in used_ids]
    if eligible:
        return eligible

    for fallback_tier in tier_fallback_candidates(tier_name):
        eligible = [
            b
            for b in tier_pools.get(fallback_tier[0], [])
            if b["book_id"] not in used_ids
        ]
        if eligible:
            return eligible

    return []


async def fetch_tier_row(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    tier: typing.Tuple[str, float, float, float],
    used_ids: typing.AbstractSet[int] = frozenset(),
) -> typing.Optional[typing.Any]:
    row = await _fetch_random_book_from_tier(
        session, language, tier[1], tier[2], RARITY_MIN_RATINGS[tier[0]]
    )
    if row is not None and row.book_id not in used_ids:
        return row
    return None


async def fetch_tier_row_with_fallback(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    tier: typing.Tuple[str, float, float, float],
    used_ids: typing.AbstractSet[int] = frozenset(),
) -> typing.Optional[typing.Any]:
    row = await _fetch_random_book_from_tier(
        session, language, tier[1], tier[2], RARITY_MIN_RATINGS[tier[0]]
    )
    if row is not None and row.book_id not in used_ids:
        return row

    for fallback_tier in tier_fallback_candidates(tier[0]):
        row = await _fetch_random_book_from_tier(
            session,
            language,
            fallback_tier[1],
            fallback_tier[2],
            RARITY_MIN_RATINGS[fallback_tier[0]],
        )
        if row is not None and row.book_id not in used_ids:
            return row

    return None


async def _fetch_random_book_from_tier(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    min_rating: float,
    max_rating: float,
    min_ratings: int,
) -> typing.Optional[typing.Any]:
    boost = app.services._language_boost.lang_boost_sql()
    query = sqlalchemy.text(
        _BOOK_SELECT
        + f"""
        WHERE (b.rating_count + b.ol_rating_count) >= :min_ratings
          AND {_COMBINED_RATING_FILTER}
        """
        + _BOOK_GROUP_BY
        + f"""
        ORDER BY RANDOM() * {boost} DESC
        LIMIT 1
        """
    )
    result = await session.execute(
        query,
        {
            "language": language,
            "min_rating": min_rating,
            "max_rating": max_rating,
            "min_ratings": min_ratings,
        },
    )
    return result.first()


def _compute_rarity(combined_rating: float) -> str:
    if combined_rating > 4.75:
        return "legendary"
    if combined_rating > 4.50:
        return "ultra_rare"
    if combined_rating > 4.00:
        return "super_rare"
    if combined_rating > 3.25:
        return "rare"
    if combined_rating > 2.25:
        return "uncommon"
    return "common"


def row_to_case_item(row: typing.Any) -> typing.Dict[str, typing.Any]:
    combined = float(row.combined_rating) if row.combined_rating else 0.0

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
        "language": getattr(row, "language", "") or "",
        "authors": authors,
        "rarity": _compute_rarity(combined),
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
