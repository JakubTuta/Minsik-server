import logging
import typing

import app.cache
import app.config
import app.services.personal_builder
import app.services.taste_profile

logger = logging.getLogger(__name__)


async def get_personal_home_sections(
    user_id: int,
    limit_per_section: int,
    cache_only: bool = False,
    force_refresh: bool = False,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    import app.db

    cache_key = f"rec:personal:{user_id}"
    if not force_refresh:
        cached = await app.cache.get_cached(cache_key)
        if cached is not None:
            return cached

    if cache_only:
        return None

    if force_refresh:
        await app.cache.invalidate_user_personal_recommendations(user_id)

    profile = await app.services.taste_profile.get_taste_profile(
        user_id,
        force_refresh=force_refresh,
    )
    if profile is None or profile.get("is_cold_start"):
        await app.cache.set_cached(
            cache_key, [], app.config.settings.cache_personal_ttl
        )
        return []

    sections = await app.services.personal_builder.build_personal_home_sections(
        app.db.async_session_maker, profile, limit_per_section
    )

    await app.cache.set_cached(
        cache_key, sections, app.config.settings.cache_personal_ttl
    )
    return sections


async def get_personal_book_sections(
    user_id: int,
    book_id: int,
    limit_per_section: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    import app.db

    cache_key = f"rec:personal:book:{user_id}:{book_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    profile = await app.services.taste_profile.get_taste_profile(user_id)
    if profile is None or profile.get("is_cold_start"):
        return []

    async with app.db.async_session_maker() as session:
        sections = await app.services.personal_builder.build_personal_book_sections(
            session, book_id, profile, limit_per_section
        )

    await app.cache.set_cached(
        cache_key, sections, app.config.settings.cache_personal_contextual_ttl
    )
    return sections


async def get_personal_author_sections(
    user_id: int,
    author_id: int,
    limit_per_section: int,
) -> typing.List[typing.Dict[str, typing.Any]]:
    import app.db

    cache_key = f"rec:personal:author:{user_id}:{author_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    profile = await app.services.taste_profile.get_taste_profile(user_id)
    if profile is None or profile.get("is_cold_start"):
        return []

    async with app.db.async_session_maker() as session:
        sections = await app.services.personal_builder.build_personal_author_sections(
            session, author_id, profile, limit_per_section
        )

    await app.cache.set_cached(
        cache_key, sections, app.config.settings.cache_personal_contextual_ttl
    )
    return sections
