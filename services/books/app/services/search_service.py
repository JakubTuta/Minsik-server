import typing
import logging
import math
import datetime
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.sql.functions as func
from sqlalchemy import select, text, or_
import app.config
import app.models.book
import app.models.author
import app.models.series
import app.cache

logger = logging.getLogger(__name__)


async def search_books_and_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int = 10,
    offset: int = 0,
    type_filter: str = "all"
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"search:{hash(query)}:type:{type_filter}:limit:{limit}:offset:{offset}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["results"], cached["total"]

    results = []
    total_count = 0

    if type_filter in ["all", "books"]:
        book_results, book_total = await _search_books(session, query, limit * 2, offset)
        results.extend(book_results)
        total_count += book_total

    if type_filter in ["all", "authors"]:
        author_results, author_total = await _search_authors(session, query, limit * 2, offset)
        results.extend(author_results)
        total_count += author_total

        for author_result in author_results:
            if author_result["relevance_score"] > 0.1:
                author_books = await _get_author_top_books(
                    session,
                    author_result["id"],
                    app.config.settings.search_author_books_expansion
                )
                results.extend(author_books)

    if type_filter in ["all", "series"]:
        series_results, series_total = await _search_series(session, query, limit * 2, offset)
        results.extend(series_results)
        total_count += series_total

        for series_result in series_results:
            if series_result["relevance_score"] > 0.1:
                series_books = await _get_series_top_books(
                    session,
                    series_result["id"],
                    3
                )
                results.extend(series_books)

    seen_items = {}
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
        app.config.settings.cache_search_ttl
    )

    return final_results, total_count


async def _search_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int,
    offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    search_query = text("""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            b.view_count,
            ts_rank(b.ts_vector, plainto_tsquery('english', :query)) as text_rank,
            COALESCE(b.view_count, 0) as views,
            b.last_viewed_at,
            (
                ts_rank(b.ts_vector, plainto_tsquery('english', :query)) * :text_weight +
                (LOG(COALESCE(b.view_count, 0) + 1) *
                    CASE
                        WHEN b.last_viewed_at > NOW() - (:recent_days * INTERVAL '1 day') THEN :recent_multiplier
                        ELSE 1.0
                    END * :popularity_weight)
            ) as final_rank,
            ARRAY_AGG(a.name) FILTER (WHERE a.name IS NOT NULL) as author_names,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.ts_vector @@ plainto_tsquery('english', :query)
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.view_count, b.last_viewed_at, b.ts_vector, s.slug
        ORDER BY final_rank DESC
        LIMIT :limit OFFSET :offset
    """)

    count_query = text("""
        SELECT COUNT(DISTINCT b.book_id)
        FROM books.books b
        WHERE b.ts_vector @@ plainto_tsquery('english', :query)
    """)

    result = await session.execute(
        search_query,
        {
            "query": query,
            "text_weight": app.config.settings.text_relevance_weight,
            "popularity_weight": app.config.settings.popularity_weight,
            "recent_days": app.config.settings.recent_views_days,
            "recent_multiplier": app.config.settings.recent_views_multiplier,
            "limit": limit,
            "offset": offset
        }
    )

    count_result = await session.execute(count_query, {"query": query})
    total = count_result.scalar() or 0

    books = []
    for row in result:
        books.append({
            "type": "book",
            "id": row.book_id,
            "title": row.title,
            "slug": row.slug,
            "cover_url": row.primary_cover_url or "",
            "authors": row.author_names or [],
            "relevance_score": float(row.final_rank),
            "view_count": row.views,
            "author_slugs": row.author_slugs or [],
            "series_slug": row.series_slug or ""
        })

    return books, total


async def _search_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int,
    offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    search_query = text("""
        SELECT
            a.author_id,
            a.name,
            a.slug,
            a.photo_url,
            a.view_count,
            ts_rank(a.ts_vector, plainto_tsquery('english', :query)) as text_rank,
            COALESCE(a.view_count, 0) as views,
            a.last_viewed_at,
            (
                ts_rank(a.ts_vector, plainto_tsquery('english', :query)) * :text_weight +
                (LOG(COALESCE(a.view_count, 0) + 1) *
                    CASE
                        WHEN a.last_viewed_at > NOW() - (:recent_days * INTERVAL '1 day') THEN :recent_multiplier
                        ELSE 1.0
                    END * :popularity_weight)
            ) as final_rank
        FROM books.authors a
        WHERE a.ts_vector @@ plainto_tsquery('english', :query)
        ORDER BY final_rank DESC
        LIMIT :limit OFFSET :offset
    """)

    count_query = text("""
        SELECT COUNT(*)
        FROM books.authors a
        WHERE a.ts_vector @@ plainto_tsquery('english', :query)
    """)

    result = await session.execute(
        search_query,
        {
            "query": query,
            "text_weight": app.config.settings.text_relevance_weight,
            "popularity_weight": app.config.settings.popularity_weight,
            "recent_days": app.config.settings.recent_views_days,
            "recent_multiplier": app.config.settings.recent_views_multiplier,
            "limit": limit,
            "offset": offset
        }
    )

    count_result = await session.execute(count_query, {"query": query})
    total = count_result.scalar() or 0

    authors = []
    for row in result:
        authors.append({
            "type": "author",
            "id": row.author_id,
            "title": row.name,
            "slug": row.slug,
            "cover_url": row.photo_url or "",
            "authors": [],
            "relevance_score": float(row.final_rank),
            "view_count": row.views,
            "author_slugs": [],
            "series_slug": ""
        })

    return authors, total


async def _get_author_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    limit: int
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = text("""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            COALESCE(b.view_count, 0) as view_count,
            COALESCE(b.rating_count, 0) as rating_count,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE ba.author_id = :author_id
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.view_count, b.rating_count, b.created_at, s.slug
        ORDER BY
            COALESCE(b.view_count, 0) DESC,
            COALESCE(b.rating_count, 0) DESC,
            b.created_at DESC
        LIMIT :limit
    """)

    result = await session.execute(
        query,
        {"author_id": author_id, "limit": limit}
    )

    books = []
    for row in result:
        books.append({
            "type": "book",
            "id": row.book_id,
            "title": row.title,
            "slug": row.slug,
            "cover_url": row.primary_cover_url or "",
            "authors": [],
            "relevance_score": 0.4,
            "view_count": row.view_count,
            "author_slugs": row.author_slugs or [],
            "series_slug": row.series_slug or ""
        })

    return books


async def _search_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int,
    offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    search_query = text("""
        SELECT
            s.series_id,
            s.name,
            s.slug,
            s.view_count,
            ts_rank(s.ts_vector, plainto_tsquery('english', :query)) as text_rank,
            COALESCE(s.view_count, 0) as views,
            s.last_viewed_at,
            (
                ts_rank(s.ts_vector, plainto_tsquery('english', :query)) * :text_weight +
                (LOG(COALESCE(s.view_count, 0) + 1) *
                    CASE
                        WHEN s.last_viewed_at > NOW() - (:recent_days * INTERVAL '1 day') THEN :recent_multiplier
                        ELSE 1.0
                    END * :popularity_weight)
            ) as final_rank,
            (SELECT COUNT(*) FROM books.books b WHERE b.series_id = s.series_id) as book_count
        FROM books.series s
        WHERE s.ts_vector @@ plainto_tsquery('english', :query)
        ORDER BY final_rank DESC
        LIMIT :limit OFFSET :offset
    """)

    count_query = text("""
        SELECT COUNT(*)
        FROM books.series s
        WHERE s.ts_vector @@ plainto_tsquery('english', :query)
    """)

    result = await session.execute(
        search_query,
        {
            "query": query,
            "text_weight": app.config.settings.text_relevance_weight,
            "popularity_weight": app.config.settings.popularity_weight,
            "recent_days": app.config.settings.recent_views_days,
            "recent_multiplier": app.config.settings.recent_views_multiplier,
            "limit": limit,
            "offset": offset
        }
    )

    count_result = await session.execute(count_query, {"query": query})
    total = count_result.scalar() or 0

    series_list = []
    for row in result:
        series_list.append({
            "type": "series",
            "id": row.series_id,
            "title": row.name,
            "slug": row.slug,
            "cover_url": "",
            "authors": [f"{row.book_count} books"],
            "relevance_score": float(row.final_rank),
            "view_count": row.views,
            "author_slugs": [],
            "series_slug": ""
        })

    return series_list, total


async def _get_series_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    limit: int
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = text("""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            b.series_position,
            COALESCE(b.view_count, 0) as view_count,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.series_id = :series_id
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.series_position, b.view_count, b.created_at, s.slug
        ORDER BY
            b.series_position ASC NULLS LAST,
            b.created_at ASC
        LIMIT :limit
    """)

    result = await session.execute(
        query,
        {"series_id": series_id, "limit": limit}
    )

    books = []
    for row in result:
        books.append({
            "type": "book",
            "id": row.book_id,
            "title": row.title,
            "slug": row.slug,
            "cover_url": row.primary_cover_url or "",
            "authors": [],
            "relevance_score": 0.4,
            "view_count": row.view_count,
            "author_slugs": row.author_slugs or [],
            "series_slug": row.series_slug or ""
        })

    return books
