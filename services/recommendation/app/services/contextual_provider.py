import logging
import typing

import app.cache
import app.config
import app.db
import app.services.author_recommender
import app.services.book_recommender
import app.services.series_recommender

logger = logging.getLogger(__name__)


async def get_book_recommendations(
    book_id: int,
    limit_per_section: int,
    user_id: int = 0,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    if user_id > 0:
        return await _get_personal_book_sections(book_id, limit_per_section, user_id)

    cache_key = f"rec:book:{book_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    sections = await app.services.book_recommender.build_book_recommendations(
        app.db.async_session_maker, book_id, limit_per_section
    )

    if sections is None:
        return None

    await app.cache.set_cached(
        cache_key, sections, app.config.settings.cache_contextual_ttl
    )
    return sections


async def _get_personal_book_sections(
    book_id: int,
    limit_per_section: int,
    user_id: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    import app.services.personal_provider

    return await app.services.personal_provider.get_personal_book_sections(
        user_id, book_id, limit_per_section
    )


async def get_author_recommendations(
    author_id: int,
    limit_per_section: int,
    user_id: int = 0,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    if user_id > 0:
        return await _get_personal_author_sections(
            author_id, limit_per_section, user_id
        )

    cache_key = f"rec:author:{author_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    sections = await app.services.author_recommender.build_author_recommendations(
        app.db.async_session_maker, author_id, limit_per_section
    )

    if sections is None:
        return None

    await app.cache.set_cached(
        cache_key, sections, app.config.settings.cache_contextual_ttl
    )
    return sections


async def _get_personal_author_sections(
    author_id: int,
    limit_per_section: int,
    user_id: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    import app.services.personal_provider

    return await app.services.personal_provider.get_personal_author_sections(
        user_id, author_id, limit_per_section
    )


async def get_series_recommendations(
    series_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    cache_key = f"rec:series:{series_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    sections = await app.services.series_recommender.build_series_recommendations(
        app.db.async_session_maker, series_id, limit_per_section
    )

    if sections is None:
        return None

    await app.cache.set_cached(
        cache_key, sections, app.config.settings.cache_contextual_ttl
    )
    return sections
