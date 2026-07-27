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


# Every edition of a work, each with the language it is written in. A
# translation only becomes indexable if it has a URL of its own in the sitemap,
# and the caller turns the language into that URL's locale prefix — an edition
# in a language the app ships no locale for has no such URL and is dropped
# there rather than here.
#
# Paging is over works, not editions, so a heavily translated book cannot push
# other works past the caller's cap; a page therefore returns more rows than
# its `limit`, and the caller advances by the page size it asked for.
_BOOKS_SITEMAP_QUERY = """
    WITH ranked AS (
        SELECT
            work_id,
            MAX(COALESCE(ol_already_read_count, 0)) AS popularity,
            MIN(book_id) AS anchor_id
        FROM books.books
        GROUP BY work_id
        ORDER BY popularity DESC, anchor_id ASC
        LIMIT :limit OFFSET :offset
    )
    SELECT b.slug, b.language, b.work_id, b.updated_at
    FROM books.books b
    JOIN ranked r ON r.work_id = b.work_id
    ORDER BY r.popularity DESC, r.anchor_id ASC, (b.language = 'en') DESC, b.book_id ASC
"""

_BOOKS_SITEMAP_COUNT_QUERY = "SELECT COUNT(DISTINCT work_id) FROM books.books"


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

    if entity == "books":
        result = await session.execute(
            sqlalchemy.text(_BOOKS_SITEMAP_QUERY), {"limit": limit, "offset": offset}
        )
        rows = result.all()
        items = [
            {
                "slug": row.slug,
                "language": row.language or "en",
                "work_id": row.work_id or "",
                "updated_at": row.updated_at.isoformat() if row.updated_at else "",
            }
            for row in rows
        ]
        total_count = 0
        if offset == 0:
            count_cache_key = "sitemap:count:books"
            cached_count = await app.cache.get_cached(count_cache_key)
            if cached_count is not None:
                total_count = int(cached_count)
            else:
                count_result = await session.execute(sqlalchemy.text(_BOOKS_SITEMAP_COUNT_QUERY))
                total_count = count_result.scalar_one()
                await app.cache.set_cached(
                    count_cache_key, total_count, COUNT_CACHE_TTL_SECONDS
                )
    else:
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
                "language": "",
                "work_id": "",
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
