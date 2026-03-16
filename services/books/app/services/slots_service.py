import logging
import random
import typing

import app.services.case_service as case_service
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def spin_slots(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    language: str = "en",
) -> typing.Tuple[typing.List[str], typing.Dict[str, typing.Any]]:
    """
    Spin the slots. Returns a tuple of (reels, winner_book_dict).
    The reels are a list of 3 strings representing the tiers.
    The lowest tier in the reels equals the rarity of the winner book.
    """
    # Try getting a winner from cache (if English) or fallback to DB
    winner_item = None

    if language == "en":
        # we can use the tier pools if they are cached, but we need to pick a tier first
        tier = case_service._pick_winning_tier()

        # We need to replicate some of the cache logic
        tier_pools: typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]] = {}
        all_cached = True
        for tier_name, _, _, _ in case_service.RARITY_TIERS:
            import app.cache

            pool = await app.cache.get_cached(
                f"{case_service.CACHE_POOL_KEY_PREFIX}:{tier_name}:{language}"
            )
            if pool is None:
                all_cached = False
                break
            tier_pools[tier_name] = pool

        if all_cached:
            winner_pool = tier_pools[tier[0]]

            # fallback logic if exact pool is empty
            if not winner_pool:
                tier_index = next(
                    i
                    for i, t in enumerate(case_service.RARITY_TIERS)
                    if t[0] == tier[0]
                )
                winner_pool = None
                for i in range(1, len(case_service.RARITY_TIERS)):
                    for idx in [tier_index + i, tier_index - i]:
                        if 0 <= idx < len(case_service.RARITY_TIERS):
                            candidate = tier_pools[case_service.RARITY_TIERS[idx][0]]
                            if candidate:
                                winner_pool = candidate
                                break
                    if winner_pool:
                        break

            if winner_pool:
                winner_item = random.choice(winner_pool)
                # Ensure rarity is set based on the book, or fallback to the tier we found it in
                if "rarity" not in winner_item:
                    winner_item["rarity"] = tier[0]

    # If not found in cache or not English, fetch from DB
    if not winner_item:
        tier = case_service._pick_winning_tier()
        winner_row = await case_service._fetch_random_book_from_tier(
            session,
            language,
            tier[1],
            tier[2],
            case_service.RARITY_MIN_RATINGS[tier[0]],
        )

        if winner_row is None:
            winner_row = await case_service._fallback_book(session, language, tier)

        if winner_row is None:
            raise ValueError(f"No rated books found for language '{language}'")

        winner_item = case_service._row_to_case_item(winner_row)

    actual_winning_tier = winner_item.get("rarity", "common")

    # Generate 3 reel symbols
    # Guarantee one is actual_winning_tier
    # The other two are randomly drawn from actual_winning_tier and higher tiers.
    # Tiers are ordered highest to lowest in RARITY_TIERS.
    tier_names = [t[0] for t in case_service.RARITY_TIERS]
    try:
        winning_idx = tier_names.index(actual_winning_tier)
    except ValueError:
        winning_idx = len(tier_names) - 1
        actual_winning_tier = tier_names[winning_idx]

    # Eligible tiers: 0 to winning_idx (inclusive)
    eligible_tiers = case_service.RARITY_TIERS[: winning_idx + 1]

    total_prob = sum(t[3] for t in eligible_tiers)

    reels = [actual_winning_tier]

    for _ in range(2):
        roll = random.random() * total_prob
        cumulative = 0.0
        selected = actual_winning_tier
        for t_name, _, _, t_prob in eligible_tiers:
            cumulative += t_prob
            if roll <= cumulative:
                selected = t_name
                break
        reels.append(selected)

    random.shuffle(reels)

    return reels, winner_item
