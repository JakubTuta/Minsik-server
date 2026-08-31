import asyncio
import datetime
import logging
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

import app.cache
import app.config
import app.services.personal_builder
import app.services.taste_profile

logger = logging.getLogger(__name__)

# Cron-only personalized home means a miss shows the reader nothing, silently
# — the only way to notice a broken refresh run is to look for it. Prod runs
# LOG_LEVEL=ERROR, so a plain INFO summary is invisible; this key is what an
# admin/status page can poll instead. TTL is a few cron intervals so a status
# check still reports "stale" rather than "unknown" if the job stops running.
REFRESH_STATUS_KEY = "rec:personal:refresh:status"
REFRESH_STATUS_TTL = 3 * 86400

# Postgres is capped at 1.0 CPU; each in-flight user runs several aggregation
# queries, so more than two at once pins the container for the whole run.
_REFRESH_CONCURRENCY = 2


async def _get_active_users(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    threshold: int,
) -> typing.List[typing.Tuple[int, str]]:
    result = await session.execute(
        sqlalchemy.text("""
            SELECT bsh.user_id, COALESCE(u.preferred_language, 'en') AS preferred_language
            FROM user_data.bookshelves bsh
            JOIN auth.users u ON u.user_id = bsh.user_id
            GROUP BY bsh.user_id, u.preferred_language
            HAVING COUNT(DISTINCT bsh.book_id) >= :threshold
        """),
        {"threshold": threshold},
    )
    pairs: typing.Set[typing.Tuple[int, str]] = {
        (row.user_id, row.preferred_language) for row in result.fetchall()
    }

    # Also warm every locale a user has actually requested, not just their
    # stored preferred_language — grpc/server.py's GetHomePage records one on
    # every real request. Without this, switching UI locale writes a cache
    # key the cron never rebuilds, so it stays empty forever instead of for
    # a day.
    for user_id, _ in list(pairs):
        seen = await app.cache.get_seen_locales(user_id)
        for language in seen:
            pairs.add((user_id, language))

    return list(pairs)


async def refresh_user_personal(
    session_maker: typing.Any,
    user_id: int,
    language: str = "en",
) -> None:
    profile = await app.services.taste_profile.build_taste_profile(session_maker, user_id)

    profile_key = f"rec:profile:{user_id}"
    await app.cache.set_cached(profile_key, profile, app.config.settings.cache_profile_ttl)

    if profile.get("is_cold_start"):
        return

    sections = await app.services.personal_builder.build_personal_home_sections(
        session_maker, profile, app.config.settings.list_default_size, language
    )

    sections_key = f"rec:personal:{user_id}:{language}"
    await app.cache.set_cached(sections_key, sections, app.config.settings.cache_personal_ttl)


async def refresh_all_personal(session_maker: typing.Any) -> None:
    threshold = app.config.settings.personal_cold_start_threshold

    async with session_maker() as session:
        users = await _get_active_users(session, threshold)

    logger.info(f"[rec:personal] Refreshing {len(users)} users")

    semaphore = asyncio.Semaphore(_REFRESH_CONCURRENCY)
    success_count = 0
    error_count = 0

    async def refresh_with_limit(uid: int, language: str) -> None:
        nonlocal success_count, error_count
        async with semaphore:
            try:
                await refresh_user_personal(session_maker, uid, language)
                success_count += 1
            except Exception:
                logger.exception(f"[rec:personal] Error refreshing user {uid}")
                error_count += 1

    await asyncio.gather(*[refresh_with_limit(uid, language) for uid, language in users])

    summary = (
        f"[rec:personal] Refresh complete: {success_count} succeeded, "
        f"{error_count} failed"
    )
    if error_count > 0:
        logger.warning(summary)
    else:
        logger.info(summary)

    await app.cache.set_cached(
        REFRESH_STATUS_KEY,
        {
            "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_users": len(users),
            "success_count": success_count,
            "error_count": error_count,
        },
        REFRESH_STATUS_TTL,
    )
