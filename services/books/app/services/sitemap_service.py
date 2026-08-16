import logging
import typing

import app.cache
import app.models.author
import app.models.book
import app.models.series
import app.services._language_boost
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
# The sitemap ranks works by the same signal category listings sort by — every
# shelf status on either side plus every rating — so what the crawler is pointed
# at first is what the app itself treats as most popular. Taken per edition and
# reduced with MAX: the shelf rollup is already per work, and a work's Open
# Library counts sit on whichever edition Open Library recorded them against.
_BOOKS_SITEMAP_QUERY = f"""
    WITH ranked AS (
        SELECT
            b.work_id,
            MAX({app.services._language_boost.work_popularity_sql()}) AS popularity,
            MIN(b.book_id) AS anchor_id
        FROM books.books b
        {app.services._language_boost.work_shelf_counts_join()}
        GROUP BY b.work_id
        ORDER BY popularity DESC, anchor_id ASC
        LIMIT :limit OFFSET :offset
    )
    SELECT b.slug, b.language, b.work_id, b.updated_at
    FROM books.books b
    JOIN ranked r ON r.work_id = b.work_id
    {{language_filter}}
    ORDER BY r.popularity DESC, r.anchor_id ASC, (b.language = 'en') DESC, b.book_id ASC
"""

_BOOKS_LANGUAGE_FILTER = "WHERE b.language IS NULL OR b.language IN :languages"

_BOOKS_SITEMAP_COUNT_QUERY = "SELECT COUNT(DISTINCT work_id) FROM books.books"


def _books_statement(
    languages: typing.Sequence[str],
) -> typing.Tuple[typing.Any, typing.Dict[str, typing.Any]]:
    if not languages:
        return sqlalchemy.text(_BOOKS_SITEMAP_QUERY.format(language_filter="")), {}

    statement = sqlalchemy.text(
        _BOOKS_SITEMAP_QUERY.format(language_filter=_BOOKS_LANGUAGE_FILTER)
    ).bindparams(sqlalchemy.bindparam("languages", expanding=True))
    return statement, {"languages": list(languages)}


async def list_sitemap_slugs(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    entity: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    languages: typing.Optional[typing.Sequence[str]] = None,
) -> typing.Tuple[typing.List[typing.Dict[str, str]], int]:
    if entity not in SITEMAP_ENTITIES:
        raise ValueError(f"Invalid sitemap entity: {entity}")

    languages = sorted(set(languages or ()))
    language_key = ",".join(languages) if entity == "books" else ""
    cache_key = f"sitemap:slugs:{entity}:{limit}:{offset}:{language_key}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached["items"], cached["total_count"]

    if entity == "books":
        statement, language_params = _books_statement(languages)
        result = await session.execute(
            statement, {"limit": limit, "offset": offset, **language_params}
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
