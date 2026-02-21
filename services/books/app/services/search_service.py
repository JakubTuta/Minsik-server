import datetime
import logging
import typing

import app.cache
import app.config
import app.es_client
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def search_books_and_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int = 10,
    offset: int = 0,
    type_filter: str = "all",
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"search:{hash(query)}:type:{type_filter}:limit:{limit}:offset:{offset}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["results"], cached["total"]

    results = []
    total_count = 0

    if type_filter in ["all", "books"]:
        book_results, book_total = await _search_books_es(query, limit * 2, offset)
        results.extend(book_results)
        total_count += book_total

    if type_filter in ["all", "authors"]:
        author_results, author_total = await _search_authors_es(
            query, limit * 2, offset
        )
        results.extend(author_results)
        total_count += author_total

        for author_result in author_results:
            if author_result["relevance_score"] > 0.1:
                author_books = await _get_author_top_books(
                    session,
                    author_result["id"],
                    app.config.settings.search_author_books_expansion,
                )
                results.extend(author_books)

    if type_filter in ["all", "series"]:
        series_results, series_total = await _search_series_es(query, limit * 2, offset)
        results.extend(series_results)
        total_count += series_total

        for series_result in series_results:
            if series_result["relevance_score"] > 0.1:
                series_books = await _get_series_top_books(
                    session, series_result["id"], 3
                )
                results.extend(series_books)

    seen_items: typing.Dict[typing.Tuple[str, int], typing.Dict[str, typing.Any]] = {}
    for result in results:
        key = (result["type"], result["id"])
        if key not in seen_items:
            seen_items[key] = result
        else:
            if result["relevance_score"] > seen_items[key]["relevance_score"]:
                seen_items[key] = result

    deduplicated_results = list(seen_items.values())
    deduplicated_results.sort(key=lambda x: x["relevance_score"], reverse=True)

    final_results = deduplicated_results[:limit]

    await app.cache.set_cached(
        cache_key,
        {"results": final_results, "total": total_count},
        app.config.settings.cache_search_ttl,
    )

    return final_results, total_count


def _build_function_score_query(
    query: str, fields: typing.List[str]
) -> typing.Dict[str, typing.Any]:
    return {
        "function_score": {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": fields,
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "functions": [
                {
                    "field_value_factor": {
                        "field": "view_count",
                        "modifier": "log1p",
                        "factor": 1.0,
                        "missing": 0,
                    },
                    "weight": 0.3,
                },
                {
                    "gauss": {"last_viewed_at": {"scale": "7d", "decay": 0.5}},
                    "weight": 0.3,
                },
            ],
            "score_mode": "sum",
            "boost_mode": "sum",
        }
    }


async def _search_books_es(
    query: str, limit: int, offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    index = app.config.settings.es_index_books

    es_query = _build_function_score_query(
        query, ["title^3", "authors_names^2", "description", "series_name"]
    )

    response = await es.search(
        index=index,
        body={
            "query": es_query,
            "from": offset,
            "size": limit,
            "_source": [
                "book_id",
                "title",
                "slug",
                "primary_cover_url",
                "authors_names",
                "author_slugs",
                "series_slug",
                "view_count",
                "avg_rating",
                "rating_count",
            ],
        },
    )

    total = response["hits"]["total"]["value"]
    books = []
    for hit in response["hits"]["hits"]:
        src = hit["_source"]
        authors_names = src.get("authors_names") or []
        if isinstance(authors_names, str):
            authors_names = [authors_names]
        author_slugs = src.get("author_slugs") or []
        if isinstance(author_slugs, str):
            author_slugs = [author_slugs]

        books.append(
            {
                "type": "book",
                "id": src["book_id"],
                "title": src.get("title", ""),
                "slug": src.get("slug", ""),
                "cover_url": src.get("primary_cover_url") or "",
                "authors": authors_names,
                "relevance_score": float(hit["_score"] or 0),
                "view_count": src.get("view_count") or 0,
                "author_slugs": author_slugs,
                "series_slug": src.get("series_slug") or "",
                "avg_rating": src.get("avg_rating"),
                "rating_count": src.get("rating_count") or 0,
                "book_count": 0,
            }
        )

    return books, total


async def _search_authors_es(
    query: str, limit: int, offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    index = app.config.settings.es_index_authors

    es_query = _build_function_score_query(query, ["name^3", "bio"])

    response = await es.search(
        index=index,
        body={
            "query": es_query,
            "from": offset,
            "size": limit,
            "_source": [
                "author_id",
                "name",
                "slug",
                "photo_url",
                "view_count",
                "book_count",
                "avg_rating",
                "rating_count",
            ],
        },
    )

    total = response["hits"]["total"]["value"]
    authors = []
    for hit in response["hits"]["hits"]:
        src = hit["_source"]
        authors.append(
            {
                "type": "author",
                "id": src["author_id"],
                "title": src.get("name", ""),
                "slug": src.get("slug", ""),
                "cover_url": src.get("photo_url") or "",
                "authors": [],
                "relevance_score": float(hit["_score"] or 0),
                "view_count": src.get("view_count") or 0,
                "author_slugs": [],
                "series_slug": "",
                "avg_rating": src.get("avg_rating"),
                "rating_count": src.get("rating_count") or 0,
                "book_count": src.get("book_count") or 0,
            }
        )

    return authors, total


async def _search_series_es(
    query: str, limit: int, offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    index = app.config.settings.es_index_series

    es_query = _build_function_score_query(query, ["name^3", "description"])

    response = await es.search(
        index=index,
        body={
            "query": es_query,
            "from": offset,
            "size": limit,
            "_source": [
                "series_id",
                "name",
                "slug",
                "view_count",
                "book_count",
                "avg_rating",
                "rating_count",
            ],
        },
    )

    total = response["hits"]["total"]["value"]
    series_list = []
    for hit in response["hits"]["hits"]:
        src = hit["_source"]
        series_list.append(
            {
                "type": "series",
                "id": src["series_id"],
                "title": src.get("name", ""),
                "slug": src.get("slug", ""),
                "cover_url": "",
                "authors": [],
                "relevance_score": float(hit["_score"] or 0),
                "view_count": src.get("view_count") or 0,
                "author_slugs": [],
                "series_slug": "",
                "avg_rating": src.get("avg_rating"),
                "rating_count": src.get("rating_count") or 0,
                "book_count": src.get("book_count") or 0,
            }
        )

    return series_list, total


async def _get_author_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int, limit: int
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = text(
        """
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            COALESCE(b.view_count, 0) as view_count,
            COALESCE(b.rating_count, 0) as rating_count,
            b.avg_rating,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE ba.author_id = :author_id
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.view_count, b.rating_count, b.avg_rating, b.created_at, s.slug
        ORDER BY
            COALESCE(b.view_count, 0) DESC,
            COALESCE(b.rating_count, 0) DESC,
            b.created_at DESC
        LIMIT :limit
    """
    )

    result = await session.execute(query, {"author_id": author_id, "limit": limit})

    books = []
    for row in result:
        books.append(
            {
                "type": "book",
                "id": row.book_id,
                "title": row.title,
                "slug": row.slug,
                "cover_url": row.primary_cover_url or "",
                "authors": [],
                "relevance_score": 0.4,
                "view_count": row.view_count,
                "author_slugs": row.author_slugs or [],
                "series_slug": row.series_slug or "",
                "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                "rating_count": row.rating_count,
                "book_count": 0,
            }
        )

    return books


async def _get_series_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession, series_id: int, limit: int
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = text(
        """
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            b.series_position,
            COALESCE(b.view_count, 0) as view_count,
            COALESCE(b.rating_count, 0) as rating_count,
            b.avg_rating,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.series_id = :series_id
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.series_position, b.view_count, b.rating_count, b.avg_rating, b.created_at, s.slug
        ORDER BY
            b.series_position ASC NULLS LAST,
            b.created_at ASC
        LIMIT :limit
    """
    )

    result = await session.execute(query, {"series_id": series_id, "limit": limit})

    books = []
    for row in result:
        books.append(
            {
                "type": "book",
                "id": row.book_id,
                "title": row.title,
                "slug": row.slug,
                "cover_url": row.primary_cover_url or "",
                "authors": [],
                "relevance_score": 0.4,
                "view_count": row.view_count,
                "author_slugs": row.author_slugs or [],
                "series_slug": row.series_slug or "",
                "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                "rating_count": row.rating_count,
                "book_count": 0,
            }
        )

    return books
