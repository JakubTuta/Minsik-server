import logging
import random
import typing

import app.services.case_service
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
        cached = await _try_pack_from_cache(length)
        if cached is not None:
            return cached

    return await _build_pack_from_db(session, language, length)


def _lowest_rarity_index(items: typing.List[typing.Dict[str, typing.Any]]) -> int:
    return min(
        range(len(items)),
        key=lambda i: _RARITY_RANK.get(items[i].get("rarity", "common"), 0),
    )


def _has_guaranteed_rarity(items: typing.List[typing.Dict[str, typing.Any]]) -> bool:
    return any(item.get("rarity") in _GUARANTEED_TIERS for item in items)


async def _try_pack_from_cache(
    length: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    tier_pools = await app.services.case_service.load_cached_tier_pools()
    if tier_pools is None:
        return None

    items = _pick_from_pools(tier_pools, length)
    if items is None:
        return None

    return _ensure_guaranteed_rarity(items, tier_pools)


def _pick_from_pools(
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]],
    length: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    items: typing.List[typing.Dict[str, typing.Any]] = []
    used_ids: typing.Set[int] = set()

    for _ in range(length):
        tier = app.services.case_service.pick_winning_tier()
        eligible = app.services.case_service.eligible_pool_books(
            tier_pools, tier[0], used_ids
        )
        if not eligible:
            return None

        book = random.choice(eligible)
        used_ids.add(book["book_id"])
        items.append(book)

    return items


def _ensure_guaranteed_rarity(
    items: typing.List[typing.Dict[str, typing.Any]],
    tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]],
) -> typing.List[typing.Dict[str, typing.Any]]:
    if _has_guaranteed_rarity(items):
        return items

    lowest_idx = _lowest_rarity_index(items)
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
        tier = app.services.case_service.pick_winning_tier()
        row = await app.services.case_service.fetch_tier_row_with_fallback(
            session, language, tier, used_ids
        )

        if row is None:
            raise ValueError(f"No rated books found for language '{language}'")

        used_ids.add(row.book_id)
        items.append(app.services.case_service.row_to_case_item(row))

    return await _ensure_guaranteed_rarity_from_db(session, language, items, used_ids)


async def _ensure_guaranteed_rarity_from_db(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
    items: typing.List[typing.Dict[str, typing.Any]],
    used_ids: typing.Set[int],
) -> typing.List[typing.Dict[str, typing.Any]]:
    if _has_guaranteed_rarity(items):
        return items

    lowest_idx = _lowest_rarity_index(items)
    replacement_ids = used_ids - {items[lowest_idx]["book_id"]}

    for tier_name in _UPGRADE_TIER_ORDER:
        tier = next(
            t for t in app.services.case_service.RARITY_TIERS if t[0] == tier_name
        )
        row = await app.services.case_service.fetch_tier_row(
            session, language, tier, replacement_ids
        )
        if row is not None:
            items[lowest_idx] = app.services.case_service.row_to_case_item(row)
            return items

    return items
