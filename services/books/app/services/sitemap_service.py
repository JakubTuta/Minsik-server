import logging
import typing

import app.cache
import app.models.author
import app.models.book
import app.models.series
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

SITEMAP_ENTITIES = ("books", "authors", "series")
DEFAULT_LIMIT = 1000
MAX_LIMIT = 10000
COUNT_CACHE_TTL_SECONDS = 3600
SLUGS_CACHE_TTL_SECONDS = 3600


def _entity_query_config(
    entity: str,
) -> typing.Tuple[typing.Any, typing.Any, typing.Any, typing.Tuple[typing.Any, ...]]:
    if entity == "books":
        model = app.models.book.Book
        return (
            model,
            model.slug,
            model.updated_at,
            (model.ol_already_read_count.desc(), model.book_id.asc()),
        )
    if entity == "authors":
        model = app.models.author.Author
        return (
            model,
            model.slug,
            model.updated_at,
            (model.view_count.desc(), model.author_id.asc()),
        )
    model = app.models.series.Series
    return (
        model,
        model.slug,
        model.updated_at,
        (model.view_count.desc(), model.series_id.asc()),
    )


async def list_sitemap_slugs(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    entity: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> typing.Tuple[typing.List[typing.Dict[str, str]], int]:
    if entity not in SITEMAP_ENTITIES:
        raise ValueError(f"Invalid sitemap entity: {entity}")

    cache_key = f"sitemap:slugs:{entity}:{limit}:{offset}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached["items"], cached["total_count"]

    model, slug_column, updated_at_column, order_by = _entity_query_config(entity)

    stmt = (
        sqlalchemy.select(slug_column, updated_at_column)
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    rows = result.all()

    items = [
        {
            "slug": slug,
            "updated_at": updated_at.isoformat() if updated_at else "",
        }
        for slug, updated_at in rows
    ]

    total_count = 0
    if offset == 0:
        total_count = await _get_entity_count(session, entity, model)

    await app.cache.set_cached(
        cache_key, {"items": items, "total_count": total_count}, SLUGS_CACHE_TTL_SECONDS
    )

    return items, total_count


async def _get_entity_count(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    entity: str,
    model: typing.Any,
) -> int:
    cache_key = f"sitemap:count:{entity}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return int(cached)

    count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(model)
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar_one()

    await app.cache.set_cached(cache_key, total_count, COUNT_CACHE_TTL_SECONDS)
    return total_count
