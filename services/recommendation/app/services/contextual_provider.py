import logging
import typing

import app.cache
import app.config
import app.db
import app.services.author_recommender
import app.services.book_recommender

logger = logging.getLogger(__name__)


async def get_book_recommendations(
    book_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    cache_key = f"rec:book:{book_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    async with app.db.async_session_maker() as session:
        sections = await app.services.book_recommender.build_book_recommendations(
            session, book_id, limit_per_section
        )

    if sections is None:
        return None

    await app.cache.set_cached(cache_key, sections, app.config.settings.cache_contextual_ttl)
    return sections


async def get_author_recommendations(
    author_id: int,
    limit_per_section: int,
) -> typing.Optional[typing.List[typing.Dict[str, typing.Any]]]:
    cache_key = f"rec:author:{author_id}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    async with app.db.async_session_maker() as session:
        sections = await app.services.author_recommender.build_author_recommendations(
            session, author_id, limit_per_section
        )

    if sections is None:
        return None

    await app.cache.set_cached(cache_key, sections, app.config.settings.cache_contextual_ttl)
    return sections
