import logging
import typing

import sqlalchemy
import sqlalchemy.ext.asyncio

import app.cache
import app.config
import app.services.personal_builder
import app.services.taste_profile

logger = logging.getLogger(__name__)


async def _get_active_user_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    threshold: int,
) -> typing.List[int]:
    result = await session.execute(
        sqlalchemy.text("""
            SELECT user_id
            FROM user_data.bookshelves
            GROUP BY user_id
            HAVING COUNT(DISTINCT book_id) >= :threshold
        """),
        {"threshold": threshold},
    )
    return [row.user_id for row in result.fetchall()]


async def _refresh_user(
    session_maker: typing.Any,
    user_id: int,
) -> None:
    async with session_maker() as session:
        profile = await app.services.taste_profile.build_taste_profile(session, user_id)

    profile_key = f"rec:profile:{user_id}"
    await app.cache.set_cached(profile_key, profile, app.config.settings.cache_profile_ttl)

    if profile.get("is_cold_start"):
        return

    sections = await app.services.personal_builder.build_personal_home_sections(
        session_maker, profile, app.config.settings.list_default_size
    )

    sections_key = f"rec:personal:{user_id}"
    await app.cache.set_cached(sections_key, sections, app.config.settings.cache_personal_ttl)


async def refresh_all_personal(session_maker: typing.Any) -> None:
    threshold = app.config.settings.personal_cold_start_threshold

    async with session_maker() as session:
        user_ids = await _get_active_user_ids(session, threshold)

    logger.info(f"[rec:personal] Refreshing {len(user_ids)} users")

    success_count = 0
    error_count = 0
    for user_id in user_ids:
        try:
            await _refresh_user(session_maker, user_id)
            success_count += 1
        except Exception as e:
            logger.error(f"[rec:personal] Error refreshing user {user_id}: {e}")
            error_count += 1

    logger.info(
        f"[rec:personal] Refresh complete: {success_count} succeeded, {error_count} failed"
    )
