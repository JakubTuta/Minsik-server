import asyncio
import logging
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

import app.cache
import app.config
import app.services.personal_builder
import app.services.taste_profile

logger = logging.getLogger(__name__)


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
    return [(row.user_id, row.preferred_language) for row in result.fetchall()]


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

    semaphore = asyncio.Semaphore(5)
    success_count = 0
    error_count = 0

    async def refresh_with_limit(uid: int, language: str) -> None:
        nonlocal success_count, error_count
        async with semaphore:
            try:
                await refresh_user_personal(session_maker, uid, language)
                success_count += 1
            except Exception as e:
                logger.error(f"[rec:personal] Error refreshing user {uid}: {e}")
                error_count += 1

    await asyncio.gather(*[refresh_with_limit(uid, language) for uid, language in users])

    logger.info(
        f"[rec:personal] Refresh complete: {success_count} succeeded, {error_count} failed"
    )
