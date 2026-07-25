import logging
import random
import typing

import app.services.case_service
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

REEL_COUNT = 3


async def spin_slots(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str = "en",
) -> typing.Tuple[typing.List[str], typing.Dict[str, typing.Any]]:
    winner_item = await _pick_winner_from_cache(language)

    if not winner_item:
        winner_item = await _pick_winner_from_db(session, language)

    winning_tier_name = winner_item.get("rarity", "common")
    reels = _build_reels(winning_tier_name)

    return reels, winner_item


async def _pick_winner_from_cache(
    language: str,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    tier_pools = await app.services.case_service.load_cached_tier_pools()
    if tier_pools is None:
        return None

    tier = app.services.case_service.pick_winning_tier()
    winner_pool = app.services.case_service.eligible_pool_books(
        tier_pools, tier[0], frozenset()
    )
    if not winner_pool:
        return None

    winner_item = app.services.case_service.pick_weighted_from_pool(winner_pool, language)
    if "rarity" not in winner_item:
        winner_item["rarity"] = tier[0]
    return winner_item


async def _pick_winner_from_db(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str,
) -> typing.Dict[str, typing.Any]:
    tier = app.services.case_service.pick_winning_tier()
    winner_row = await app.services.case_service.fetch_tier_row_with_fallback(
        session, language, tier
    )

    if winner_row is None:
        raise ValueError(f"No rated books found for language '{language}'")

    return app.services.case_service.row_to_case_item(winner_row)


def _build_reels(winning_tier_name: str) -> typing.List[str]:
    tiers = app.services.case_service.RARITY_TIERS
    tier_names = [t[0] for t in tiers]
    try:
        winning_idx = tier_names.index(winning_tier_name)
    except ValueError:
        winning_idx = len(tier_names) - 1
        winning_tier_name = tier_names[winning_idx]

    eligible_tiers = tiers[: winning_idx + 1]
    total_prob = sum(t[3] for t in eligible_tiers)

    reels = [winning_tier_name]
    for _ in range(REEL_COUNT - 1):
        roll = random.random() * total_prob
        cumulative = 0.0
        selected = winning_tier_name
        for tier_name, _, _, tier_prob in eligible_tiers:
            cumulative += tier_prob
            if roll <= cumulative:
                selected = tier_name
                break
        reels.append(selected)

    random.shuffle(reels)
    return reels
