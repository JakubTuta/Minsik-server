import logging
import random
import typing

import app.cache
import sqlalchemy
import sqlalchemy.ext.asyncio
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
    "legendary": 30,
    "ultra_rare": 20,
    "super_rare": 15,
    "rare": 8,
    "uncommon": 3,
    "common": 1,
}

DISPLAY_LIST_SIZE = 25
WINNING_INDEX = DISPLAY_LIST_SIZE - 3

DISPLAY_SLOTS: typing.Dict[str, int] = {
    "legendary": 1,
    "ultra_rare": 1,
    "super_rare": 2,
    "rare": 5,
    "uncommon": 7,
    "common": 8,
}

CACHE_POOL_KEY_PREFIX = "case:pool"

_BOOK_SELECT = """
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
            book_id,
            COUNT(*) FILTER (WHERE status = 'want_to_read') AS app_want_to_read_count,
            COUNT(*) FILTER (WHERE status = 'reading') AS app_reading_count,
            COUNT(*) FILTER (WHERE status = 'read') AS app_read_count
        FROM user_data.bookshelves
        WHERE status != 'abandoned'
        GROUP BY book_id
    ) bs ON b.book_id = bs.book_id
"""

_BOOK_GROUP_BY = """
    GROUP BY b.book_id, b.title, b.slug, b.description, b.primary_cover_url,
             b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
             b.ol_want_to_read_count, b.ol_currently_reading_count,
             b.ol_already_read_count, bs.app_want_to_read_count,
             bs.app_reading_count, bs.app_read_count
"""

_COMBINED_RATING_FILTER = """
    (
        COALESCE(b.avg_rating::numeric, 0) * b.rating_count
        + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
    ) / (b.rating_count + b.ol_rating_count) > :min_rating
    AND (
        COALESCE(b.avg_rating::numeric, 0) * b.rating_count
        + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
    ) / (b.rating_count + b.ol_rating_count) <= :max_rating
"""


async def open_case(
    session: sqlalchemy.ext.asyncio.AsyncSession, language: str
) -> typing.Dict[str, typing.Any]:
    if language == "en":
        cached_result = await _try_open_from_cache(language)
        if cached_result is not None:
            return cached_result

    tier = _pick_winning_tier()
    winner_row = await _fetch_random_book_from_tier(
        session, language, tier[1], tier[2], RARITY_MIN_RATINGS[tier[0]]
    )

    if winner_row is None:
        winner_row = await _fallback_book(session, language, tier)

    if winner_row is None:
        raise ValueError(f"No rated books found for language '{language}'")

    winner_item = _row_to_case_item(winner_row)
    display_books = await _build_display_list(session, language, winner_row.book_id)
    actual_winning_index = min(WINNING_INDEX, len(display_books))
    display_books.insert(actual_winning_index, winner_item)

    return {
        "display_list": display_books,
        "winning_index": actual_winning_index,
        "winner": winner_item,
    }


async def _try_open_from_cache(
    language: str,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {}
    for tier_name, _, _, _ in RARITY_TIERS:
        pool = await app.cache.get_cached(
            f"{CACHE_POOL_KEY_PREFIX}:{tier_name}:{language}"
        )
        if pool is None:
            return None
        tier_pools[tier_name] = pool

    winning_tier = _pick_winning_tier()
    winner_pool = tier_pools[winning_tier[0]]

    if not winner_pool:
        tier_index = next(
            i for i, t in enumerate(RARITY_TIERS) if t[0] == winning_tier[0]
        )
        winner_pool = None
        for i in range(1, len(RARITY_TIERS)):
            for idx in [tier_index + i, tier_index - i]:
                if 0 <= idx < len(RARITY_TIERS):
                    candidate = tier_pools[RARITY_TIERS[idx][0]]
                    if candidate:
                        winner_pool = candidate
                        break
            if winner_pool:
                break
        if not winner_pool:
            return None

    winner = random.choice(winner_pool)

    display_books: typing.List[typing.Dict[str, typing.Any]] = []
    for tier_name, _, _, _ in RARITY_TIERS:
        slots = DISPLAY_SLOTS[tier_name]
        eligible = [
            b for b in tier_pools[tier_name] if b["book_id"] != winner["book_id"]
        ]
        display_books.extend(random.sample(eligible, min(slots, len(eligible))))

    random.shuffle(display_books)
    actual_winning_index = min(WINNING_INDEX, len(display_books))
    display_books.insert(actual_winning_index, winner)

    return {
        "display_list": display_books,
        "winning_index": actual_winning_index,
        "winner": winner,
    }


def _pick_winning_tier() -> typing.Tuple[str, float, float, float]:
    roll = random.random()
    cumulative = 0.0
    for tier in RARITY_TIERS:
        cumulative += tier[3]
        if roll < cumulative:
            return tier
    return RARITY_TIERS[-1]


async def _fetch_random_book_from_tier(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    min_rating: float,
    max_rating: float,
    min_ratings: int,
) -> typing.Optional[typing.Any]:
    query = text(
        _BOOK_SELECT
        + f"""
        WHERE b.language = :language
          AND (b.rating_count + b.ol_rating_count) >= :min_ratings
          AND {_COMBINED_RATING_FILTER}
        """
        + _BOOK_GROUP_BY
        + """
        ORDER BY RANDOM()
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


async def _fallback_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    original_tier: typing.Tuple[str, float, float, float],
) -> typing.Optional[typing.Any]:
    tier_index = next(
        (i for i, t in enumerate(RARITY_TIERS) if t[0] == original_tier[0]), None
    )
    if tier_index is None:
        return None

    candidates = []
    for i in range(1, len(RARITY_TIERS)):
        lower = tier_index + i
        higher = tier_index - i
        if lower < len(RARITY_TIERS):
            candidates.append(RARITY_TIERS[lower])
        if higher >= 0:
            candidates.append(RARITY_TIERS[higher])

    for fallback_tier in candidates:
        row = await _fetch_random_book_from_tier(
            session,
            language,
            fallback_tier[1],
            fallback_tier[2],
            RARITY_MIN_RATINGS[fallback_tier[0]],
        )
        if row is not None:
            return row

    return None


async def _build_display_list(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    winner_book_id: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    needed = DISPLAY_LIST_SIZE - 1
    rows = await _fetch_all_display_books(session, language, winner_book_id)
    books = [_row_to_case_item(r) for r in rows]

    if len(books) < needed:
        extra = await _fetch_any_rated_books(
            session,
            language,
            needed - len(books),
            winner_book_id,
            [b["book_id"] for b in books],
        )
        books.extend(extra)

    random.shuffle(books)
    return books[:needed]


async def _fetch_all_display_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    winner_book_id: int,
) -> typing.List[typing.Any]:
    query = text(
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
                COALESCE(bs.app_reading_count, 0) AS app_reading_count,
                COALESCE(bs.app_read_count, 0) AS app_read_count,
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
            WHERE b.language = :language
              AND b.book_id != :exclude_book_id
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
                    WHEN total_ratings >= 30 AND combined_rating >  4.65                        THEN 1
                    WHEN total_ratings >= 30 AND combined_rating >  4.50 AND combined_rating <= 4.65 THEN 2
                    WHEN total_ratings >= 15 AND combined_rating >  4.00 AND combined_rating <= 4.50 THEN 3
                    WHEN total_ratings >=  8 AND combined_rating >  3.25 AND combined_rating <= 4.00 THEN 4
                    WHEN total_ratings >=  3 AND combined_rating >  2.25 AND combined_rating <= 3.25 THEN 5
                    WHEN total_ratings >=  1 AND combined_rating <= 2.25                        THEN 6
                    ELSE NULL
                END AS bucket
            FROM book_stats
        ),
        sampled AS (
            SELECT *,
                ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY RANDOM()) AS rn
            FROM bucketed
            WHERE bucket IS NOT NULL
        )
        SELECT * FROM sampled
        WHERE (bucket = 1 AND rn <= 1)
           OR (bucket = 2 AND rn <= 1)
           OR (bucket = 3 AND rn <= 2)
           OR (bucket = 4 AND rn <= 5)
           OR (bucket = 5 AND rn <= 7)
           OR (bucket = 6 AND rn <= 8)
        """
    )
    result = await session.execute(
        query, {"language": language, "exclude_book_id": winner_book_id}
    )
    return result.fetchall()


async def _fetch_any_rated_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    limit: int,
    exclude_book_id: int,
    also_exclude_ids: typing.List[int],
) -> typing.List[typing.Dict[str, typing.Any]]:
    exclude_ids = [exclude_book_id] + also_exclude_ids
    query = text(
        _BOOK_SELECT
        + """
        WHERE b.language = :language
          AND b.book_id != ALL(:exclude_ids)
          AND (b.rating_count + b.ol_rating_count) > 0
        """
        + _BOOK_GROUP_BY
        + """
        ORDER BY RANDOM()
        LIMIT :limit
        """
    )
    result = await session.execute(
        query,
        {"language": language, "exclude_ids": exclude_ids, "limit": limit},
    )
    return [_row_to_case_item(r) for r in result.fetchall()]


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


def _row_to_case_item(row: typing.Any) -> typing.Dict[str, typing.Any]:
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
