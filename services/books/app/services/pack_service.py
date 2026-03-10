import logging
import typing

import app.cache
import app.services.case_service as case_service
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

DEFAULT_PACK_LENGTH = 8

_GUARANTEED_TIERS = {"legendary", "ultra_rare", "super_rare"}
_UPGRADE_TIER_ORDER = ["super_rare", "ultra_rare", "legendary"]

_RARITY_RANK: typing.Dict[str, int] = {
    "legendary": 6,
    "ultra_rare": 5,
    "super_rare": 4,
    "rare": 3,
    "uncommon": 2,
    "common": 1,
}


async def open_pack(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    length: int = DEFAULT_PACK_LENGTH,
) -> typing.List[typing.Dict[str, typing.Any]]:
    if language == "en":
        cached = await _try_pack_from_cache(language, length)
        if cached is not None:
            return cached

    return await _build_pack_from_db(session, language, length)


async def _try_pack_from_cache(
    language: str,
    length: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {}
    for tier_name, _, _, _ in case_service.RARITY_TIERS:
        pool = await app.cache.get_cached(
            f"{case_service.CACHE_POOL_KEY_PREFIX}:{tier_name}:{language}"
        )
        if pool is None:
            return None
        tier_pools[tier_name] = pool

    items = _pick_from_pools(tier_pools, length)
    if items is None:
        return None

    items = _ensure_guaranteed_rarity(items, tier_pools)
    return items


def _pick_from_pools(
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]],
    length: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    import random

    items: typing.List[typing.Dict[str, typing.Any]] = []
    used_ids: typing.Set[int] = set()

    for _ in range(length):
        tier = case_service._pick_winning_tier()
        pool = tier_pools[tier[0]]
        eligible = [b for b in pool if b["book_id"] not in used_ids]

        if not eligible:
            eligible = _find_fallback_from_pools(tier_pools, used_ids, tier[0])

        if not eligible:
            return None

        book = random.choice(eligible)
        used_ids.add(book["book_id"])
        items.append(book)

    return items


def _find_fallback_from_pools(
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]],
    used_ids: typing.Set[int],
    original_tier_name: str,
) -> typing.List[typing.Dict[str, typing.Any]]:
    tier_index = next(
        (
            i
            for i, t in enumerate(case_service.RARITY_TIERS)
            if t[0] == original_tier_name
        ),
        None,
    )
    if tier_index is None:
        return []

    for i in range(1, len(case_service.RARITY_TIERS)):
        for idx in [tier_index + i, tier_index - i]:
            if 0 <= idx < len(case_service.RARITY_TIERS):
                tier_name = case_service.RARITY_TIERS[idx][0]
                eligible = [
                    b for b in tier_pools[tier_name] if b["book_id"] not in used_ids
                ]
                if eligible:
                    return eligible

    return []


def _ensure_guaranteed_rarity(
    items: typing.List[typing.Dict[str, typing.Any]],
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]],
) -> typing.List[typing.Dict[str, typing.Any]]:
    import random

    if any(item.get("rarity") in _GUARANTEED_TIERS for item in items):
        return items

    lowest_idx = min(
        range(len(items)),
        key=lambda i: _RARITY_RANK.get(items[i].get("rarity", "common"), 0),
    )

    used_ids = {item["book_id"] for i, item in enumerate(items) if i != lowest_idx}

    for tier_name in _UPGRADE_TIER_ORDER:
        pool = tier_pools.get(tier_name, [])
        eligible = [b for b in pool if b["book_id"] not in used_ids]
        if eligible:
            items[lowest_idx] = random.choice(eligible)
            return items

    return items


async def _build_pack_from_db(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    length: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    items: typing.List[typing.Dict[str, typing.Any]] = []
    used_ids: typing.Set[int] = set()

    for _ in range(length):
        tier = case_service._pick_winning_tier()
        row = await case_service._fetch_random_book_from_tier(
            session,
            language,
            tier[1],
            tier[2],
            case_service.RARITY_MIN_RATINGS[tier[0]],
        )

        if row is None or row.book_id in used_ids:
            row = await _fetch_unique_fallback(session, language, tier, used_ids)

        if row is None:
            raise ValueError(f"No rated books found for language '{language}'")

        used_ids.add(row.book_id)
        items.append(case_service._row_to_case_item(row))

    items = await _ensure_guaranteed_rarity_from_db(session, language, items, used_ids)
    return items


async def _fetch_unique_fallback(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    original_tier: typing.Tuple[str, float, float, float],
    used_ids: typing.Set[int],
) -> typing.Optional[typing.Any]:
    tier_index = next(
        (
            i
            for i, t in enumerate(case_service.RARITY_TIERS)
            if t[0] == original_tier[0]
        ),
        None,
    )
    if tier_index is None:
        return None

    for i in range(1, len(case_service.RARITY_TIERS)):
        for idx in [tier_index + i, tier_index - i]:
            if 0 <= idx < len(case_service.RARITY_TIERS):
                fallback_tier = case_service.RARITY_TIERS[idx]
                row = await case_service._fetch_random_book_from_tier(
                    session,
                    language,
                    fallback_tier[1],
                    fallback_tier[2],
                    case_service.RARITY_MIN_RATINGS[fallback_tier[0]],
                )
                if row is not None and row.book_id not in used_ids:
                    return row

    return None


async def _ensure_guaranteed_rarity_from_db(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    items: typing.List[typing.Dict[str, typing.Any]],
    used_ids: typing.Set[int],
) -> typing.List[typing.Dict[str, typing.Any]]:
    if any(item.get("rarity") in _GUARANTEED_TIERS for item in items):
        return items

    lowest_idx = min(
        range(len(items)),
        key=lambda i: _RARITY_RANK.get(items[i].get("rarity", "common"), 0),
    )

    replacement_ids = used_ids - {items[lowest_idx]["book_id"]}

    for tier_name in _UPGRADE_TIER_ORDER:
        tier = next(t for t in case_service.RARITY_TIERS if t[0] == tier_name)
        row = await case_service._fetch_random_book_from_tier(
            session,
            language,
            tier[1],
            tier[2],
            case_service.RARITY_MIN_RATINGS[tier_name],
        )
        if row is not None and row.book_id not in replacement_ids:
            items[lowest_idx] = case_service._row_to_case_item(row)
            return items

    return items
