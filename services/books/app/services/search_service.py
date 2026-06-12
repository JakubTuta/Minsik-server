import datetime
import logging
import typing
import unicodedata

import app.cache
import app.config
import app.es_client
import app.services._language_boost
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


def _normalize_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKD", query)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


_POPULARITY_SCRIPT: str = (
    "double readers = doc['readers'].size() > 0 ? doc['readers'].value : 0;"
    " double volume = Math.log10(10 + readers);"
    " double bayes = doc['bayesian_score'].size() > 0 ? doc['bayesian_score'].value : 0;"
    " return volume * (1.0 + 0.15 * (bayes / 5.0));"
)


def _dedup_by_slug(
    results: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.List[typing.Dict[str, typing.Any]]:
    groups: typing.Dict[typing.Tuple[str, str], typing.List[typing.Dict[str, typing.Any]]] = {}
    order: typing.List[typing.Tuple[str, str]] = []
    for r in results:
        slug = r.get("slug") or ""
        if not slug:
            continue
        key = (r["type"], slug)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    out: typing.List[typing.Dict[str, typing.Any]] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            out.append(group[0])
            continue

        matched = [g for g in group if g.get("language") == language]
        if matched:
            winner = max(matched, key=lambda g: g.get("relevance_score", 0))
            out.append(winner)
            continue

        combined_readers = sum(g.get("readers") or 0 for g in group)
        winner = max(group, key=lambda g: g.get("readers") or 0)
        winner = dict(winner)
        winner["readers"] = combined_readers
        out.append(winner)

    return out


def _normalize_scores(
    results: typing.List[typing.Dict[str, typing.Any]], type_weight: float
) -> typing.List[typing.Dict[str, typing.Any]]:
    if not results:
        return results
    max_score = max(r["relevance_score"] for r in results) or 1.0
    for r in results:
        r["relevance_score"] = (r["relevance_score"] / max_score) * type_weight
    return results


_BOOKS_EXACT_FIELDS = [("title.exact", 10.0), ("authors_names.exact", 7.0), ("series_name.exact", 5.0)]
_BOOKS_PHRASE_FIELDS = [("title", 5.0), ("authors_names", 3.0), ("series_name", 2.0)]
_BOOKS_MULTI_FIELDS = ["title^3", "authors_names^2", "series_name"]
_BOOKS_PREFIX_FIELDS = [("title.exact", 4.0), ("authors_names.exact", 2.5)]
_BOOKS_SUGGEST_FIELDS = [
    "title.suggest^3",
    "title.suggest._2gram",
    "title.suggest._3gram",
    "authors_names.suggest^2",
    "authors_names.suggest._2gram",
    "authors_names.suggest._3gram",
]

_NAME_EXACT_FIELDS = [("name.exact", 10.0)]
_NAME_PHRASE_FIELDS = [("name", 5.0)]
_NAME_MULTI_FIELDS = ["name^3"]
_NAME_PREFIX_FIELDS = [("name.exact", 4.0)]
_NAME_SUGGEST_FIELDS = [
    "name.suggest^3",
    "name.suggest._2gram",
    "name.suggest._3gram",
]


def _with_popularity_and_language(
    query_part: typing.Dict[str, typing.Any], language: str
) -> typing.Dict[str, typing.Any]:
    return {
        "function_score": {
            "query": query_part,
            "functions": [
                {"script_score": {"script": {"source": _POPULARITY_SCRIPT}}},
                {
                    "filter": {"term": {"language": language}},
                    "weight": app.services._language_boost.LANGUAGE_BOOST_WEIGHT,
                },
            ],
            "score_mode": "multiply",
            "boost_mode": "multiply",
        }
    }


def _build_full_search_query(
    query: str,
    language: str,
    exact_fields: typing.List[typing.Tuple[str, float]],
    phrase_fields: typing.List[typing.Tuple[str, float]],
    multi_fields: typing.List[str],
) -> typing.Dict[str, typing.Any]:
    q_lower = _normalize_query(query)
    should: typing.List[typing.Dict[str, typing.Any]] = [
        {"term": {field: {"value": q_lower, "boost": boost}}}
        for field, boost in exact_fields
    ]
    should.extend(
        {"match_phrase": {field: {"query": query, "slop": 1, "boost": boost}}}
        for field, boost in phrase_fields
    )
    should.append(
        {
            "multi_match": {
                "query": query,
                "fields": multi_fields,
                "type": "cross_fields",
                "operator": "and",
                "tie_breaker": 0.3,
            }
        }
    )
    should.append(
        {
            "multi_match": {
                "query": query,
                "fields": multi_fields,
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO",
                "boost": 0.5,
            }
        }
    )
    return _with_popularity_and_language(
        {"bool": {"should": should, "minimum_should_match": 1}}, language
    )


def _build_suggest_query(
    query: str,
    language: str,
    prefix_fields: typing.List[typing.Tuple[str, float]],
    suggest_fields: typing.List[str],
    fuzziness: typing.Optional[str] = None,
) -> typing.Dict[str, typing.Any]:
    q_lower = _normalize_query(query)
    suggest_clause: typing.Dict[str, typing.Any] = {
        "query": query,
        "type": "bool_prefix",
        "fields": suggest_fields,
    }
    if fuzziness:
        suggest_clause["fuzziness"] = fuzziness

    should: typing.List[typing.Dict[str, typing.Any]] = [
        {"prefix": {field: {"value": q_lower, "boost": boost}}}
        for field, boost in prefix_fields
    ]
    should.append({"multi_match": suggest_clause})
    return _with_popularity_and_language(
        {"bool": {"should": should, "minimum_should_match": 1}}, language
    )


def _build_full_search_books_query(
    query: str, language: str
) -> typing.Dict[str, typing.Any]:
    return _build_full_search_query(
        query, language, _BOOKS_EXACT_FIELDS, _BOOKS_PHRASE_FIELDS, _BOOKS_MULTI_FIELDS
    )


def _build_full_search_authors_query(
    query: str, language: str
) -> typing.Dict[str, typing.Any]:
    return _build_full_search_query(
        query, language, _NAME_EXACT_FIELDS, _NAME_PHRASE_FIELDS, _NAME_MULTI_FIELDS
    )


def _build_full_search_series_query(
    query: str, language: str
) -> typing.Dict[str, typing.Any]:
    return _build_full_search_query(
        query, language, _NAME_EXACT_FIELDS, _NAME_PHRASE_FIELDS, _NAME_MULTI_FIELDS
    )


def _build_suggest_books_query(
    query: str, language: str, fuzziness: typing.Optional[str] = None
) -> typing.Dict[str, typing.Any]:
    return _build_suggest_query(
        query, language, _BOOKS_PREFIX_FIELDS, _BOOKS_SUGGEST_FIELDS, fuzziness
    )


def _build_suggest_authors_query(
    query: str, language: str, fuzziness: typing.Optional[str] = None
) -> typing.Dict[str, typing.Any]:
    return _build_suggest_query(
        query, language, _NAME_PREFIX_FIELDS, _NAME_SUGGEST_FIELDS, fuzziness
    )


def _build_suggest_series_query(
    query: str, language: str, fuzziness: typing.Optional[str] = None
) -> typing.Dict[str, typing.Any]:
    return _build_suggest_query(
        query, language, _NAME_PREFIX_FIELDS, _NAME_SUGGEST_FIELDS, fuzziness
    )


async def search_books_and_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int = 10,
    offset: int = 0,
    type_filter: str = "all",
    language: str = "en",
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"search:{query}:type:{type_filter}:limit:{limit}:offset:{offset}:lang:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["results"], cached["total"]

    results: typing.List[typing.Dict[str, typing.Any]] = []
    total_count = 0
    author_results: typing.List[typing.Dict[str, typing.Any]] = []
    series_results: typing.List[typing.Dict[str, typing.Any]] = []

    if type_filter in ["all", "books"]:
        book_results, book_total = await _search_books_es(
            query, limit, offset, language
        )
        book_results = _normalize_scores(book_results, 1.0)
        results.extend(book_results)
        total_count += book_total

    if type_filter in ["all", "authors"]:
        author_results, author_total = await _search_authors_es(
            query, limit, offset, language
        )
        author_results = _normalize_scores(author_results, 0.9)
        results.extend(author_results)
        total_count += author_total

    if type_filter == "all":
        for author_result in author_results:
            if author_result["relevance_score"] > 0.1:
                author_books = await _get_author_top_books(
                    session,
                    author_result["id"],
                    app.config.settings.search_author_books_expansion,
                    language,
                )
                expansion_score = author_result["relevance_score"] * 0.5
                for book in author_books:
                    book["relevance_score"] = expansion_score
                results.extend(author_books)

    if type_filter in ["all", "series"]:
        series_results, series_total = await _search_series_es(
            query, limit, offset, language
        )
        series_results = _normalize_scores(series_results, 0.85)
        results.extend(series_results)
        total_count += series_total

    if type_filter == "all":
        for series_result in series_results:
            if series_result["relevance_score"] > 0.1:
                series_books = await _get_series_top_books(
                    session, series_result["id"], 3, language
                )
                expansion_score = series_result["relevance_score"] * 0.5
                for book in series_books:
                    book["relevance_score"] = expansion_score
                results.extend(series_books)

    if type_filter == "categories":
        category_results, category_total = await _search_books_by_category(
            session, query, limit, offset, language
        )
        results.extend(category_results)
        total_count += category_total

    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    deduplicated_results = _dedup_by_slug(results, language)
    deduplicated_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    final_results = deduplicated_results[:limit]

    await app.cache.set_cached(
        cache_key,
        {"results": final_results, "total": total_count},
        app.config.settings.cache_search_ttl,
    )

    return final_results, total_count


async def suggest(
    query: str,
    limit: int = 8,
    language: str = "en",
) -> typing.List[typing.Dict[str, typing.Any]]:
    cache_key = f"suggest:{query}:{limit}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached

    results = await _run_suggest_queries(query, limit, language, fuzziness=None)

    if not results:
        results = await _run_suggest_queries(query, limit, language, fuzziness="AUTO")

    await app.cache.set_cached(cache_key, results, 60)
    return results


async def _run_suggest_queries(
    query: str,
    limit: int,
    language: str,
    fuzziness: typing.Optional[str],
) -> typing.List[typing.Dict[str, typing.Any]]:
    es = app.es_client.get_es()
    books_index = app.config.settings.es_index_books
    authors_index = app.config.settings.es_index_authors
    series_index = app.config.settings.es_index_series

    rating_fields = [
        "app_avg_rating",
        "app_rating_count",
        "ol_avg_rating",
        "ol_rating_count",
        "readers",
    ]

    msearch_body = [
        {"index": books_index},
        {
            "query": _build_suggest_books_query(query, language, fuzziness),
            "size": limit,
            "_source": [
                "book_id",
                "title",
                "slug",
                "primary_cover_url",
                "authors_names",
                "author_slugs",
                "language",
            ]
            + rating_fields,
        },
        {"index": authors_index},
        {
            "query": _build_suggest_authors_query(query, language, fuzziness),
            "size": limit,
            "_source": ["author_id", "name", "slug", "photo_url"] + rating_fields,
        },
        {"index": series_index},
        {
            "query": _build_suggest_series_query(query, language, fuzziness),
            "size": limit,
            "_source": ["series_id", "name", "slug"] + rating_fields,
        },
    ]

    response = await es.msearch(body=msearch_body)

    books_hits = response["responses"][0].get("hits", {}).get("hits", [])
    authors_hits = response["responses"][1].get("hits", {}).get("hits", [])
    series_hits = response["responses"][2].get("hits", {}).get("hits", [])

    books_results = []
    for hit in books_hits:
        src = hit["_source"]
        authors_names = src.get("authors_names") or []
        if isinstance(authors_names, str):
            authors_names = [authors_names]
        books_results.append(
            {
                "type": "book",
                "id": src["book_id"],
                "title": src.get("title", ""),
                "slug": src.get("slug", ""),
                "cover_url": src.get("primary_cover_url") or "",
                "authors": authors_names,
                "relevance_score": float(hit["_score"] or 0),
                "app_avg_rating": src.get("app_avg_rating"),
                "app_rating_count": src.get("app_rating_count") or 0,
                "ol_avg_rating": src.get("ol_avg_rating"),
                "ol_rating_count": src.get("ol_rating_count") or 0,
                "readers": src.get("readers") or 0,
                "language": src.get("language") or "",
            }
        )

    authors_results = []
    for hit in authors_hits:
        src = hit["_source"]
        authors_results.append(
            {
                "type": "author",
                "id": src["author_id"],
                "title": src.get("name", ""),
                "slug": src.get("slug", ""),
                "cover_url": src.get("photo_url") or "",
                "authors": [],
                "relevance_score": float(hit["_score"] or 0),
                "app_avg_rating": src.get("app_avg_rating"),
                "app_rating_count": src.get("app_rating_count") or 0,
                "ol_avg_rating": src.get("ol_avg_rating"),
                "ol_rating_count": src.get("ol_rating_count") or 0,
                "readers": src.get("readers") or 0,
            }
        )

    series_results = []
    for hit in series_hits:
        src = hit["_source"]
        series_results.append(
            {
                "type": "series",
                "id": src["series_id"],
                "title": src.get("name", ""),
                "slug": src.get("slug", ""),
                "cover_url": "",
                "authors": [],
                "relevance_score": float(hit["_score"] or 0),
                "app_avg_rating": src.get("app_avg_rating"),
                "app_rating_count": src.get("app_rating_count") or 0,
                "ol_avg_rating": src.get("ol_avg_rating"),
                "ol_rating_count": src.get("ol_rating_count") or 0,
                "readers": src.get("readers") or 0,
            }
        )

    books_results = _normalize_scores(books_results, 1.0)
    authors_results = _normalize_scores(authors_results, 0.95)
    series_results = _normalize_scores(series_results, 0.9)

    merged = books_results + authors_results + series_results
    merged.sort(key=lambda x: x["relevance_score"], reverse=True)
    merged = _dedup_by_slug(merged, language)
    merged.sort(key=lambda x: x["relevance_score"], reverse=True)
    return merged[:limit]


async def _search_books_es(
    query: str, limit: int, offset: int, language: str
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    index = app.config.settings.es_index_books

    response = await es.search(
        index=index,
        body={
            "query": _build_full_search_books_query(query, language),
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
                "app_avg_rating",
                "app_rating_count",
                "ol_avg_rating",
                "ol_rating_count",
                "readers",
                "language",
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
                "author_slugs": author_slugs,
                "series_slug": src.get("series_slug") or "",
                "app_avg_rating": src.get("app_avg_rating"),
                "app_rating_count": src.get("app_rating_count") or 0,
                "ol_avg_rating": src.get("ol_avg_rating"),
                "ol_rating_count": src.get("ol_rating_count") or 0,
                "readers": src.get("readers") or 0,
                "book_count": 0,
                "language": src.get("language") or "",
            }
        )

    return books, total


async def _search_authors_es(
    query: str, limit: int, offset: int, language: str
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    index = app.config.settings.es_index_authors

    response = await es.search(
        index=index,
        body={
            "query": _build_full_search_authors_query(query, language),
            "from": offset,
            "size": limit,
            "_source": [
                "author_id",
                "name",
                "slug",
                "photo_url",
                "book_count",
                "app_avg_rating",
                "app_rating_count",
                "ol_avg_rating",
                "ol_rating_count",
                "readers",
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
                "author_slugs": [],
                "series_slug": "",
                "app_avg_rating": src.get("app_avg_rating"),
                "app_rating_count": src.get("app_rating_count") or 0,
                "ol_avg_rating": src.get("ol_avg_rating"),
                "ol_rating_count": src.get("ol_rating_count") or 0,
                "readers": src.get("readers") or 0,
                "book_count": src.get("book_count") or 0,
            }
        )

    return authors, total


async def _search_series_es(
    query: str, limit: int, offset: int, language: str
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    index = app.config.settings.es_index_series

    response = await es.search(
        index=index,
        body={
            "query": _build_full_search_series_query(query, language),
            "from": offset,
            "size": limit,
            "_source": [
                "series_id",
                "name",
                "slug",
                "book_count",
                "app_avg_rating",
                "app_rating_count",
                "ol_avg_rating",
                "ol_rating_count",
                "readers",
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
                "author_slugs": [],
                "series_slug": "",
                "app_avg_rating": src.get("app_avg_rating"),
                "app_rating_count": src.get("app_rating_count") or 0,
                "ol_avg_rating": src.get("ol_avg_rating"),
                "ol_rating_count": src.get("ol_rating_count") or 0,
                "readers": src.get("readers") or 0,
                "book_count": src.get("book_count") or 0,
            }
        )

    return series_list, total


async def _search_books_by_category(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int,
    offset: int,
    language: str,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    count_query = sqlalchemy.text(
        """
        SELECT COUNT(DISTINCT b.book_id)
        FROM books.books b
        JOIN books.book_genres bg ON b.book_id = bg.book_id
        JOIN books.genres g ON bg.genre_id = g.genre_id
        WHERE b.language = :language
          AND (g.slug ILIKE :query_pattern OR g.name ILIKE :query_pattern)
    """
    )

    count_result = await session.execute(
        count_query,
        {"language": language, "query_pattern": f"%{query}%"},
    )
    total = count_result.scalar() or 0

    books_query = sqlalchemy.text(
        """
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            COALESCE(b.rating_count, 0) as app_rating_count,
            b.avg_rating as app_avg_rating,
            COALESCE(b.ol_rating_count, 0) as ol_rating_count,
            b.ol_avg_rating,
            b.ol_want_to_read_count + b.ol_currently_reading_count
                + b.ol_already_read_count
                + (SELECT COUNT(*) FROM user_data.bookshelves bsh
                   WHERE bsh.book_id = b.book_id
                     AND bsh.status != 'abandoned') AS readers,
            ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        JOIN books.book_genres bg ON b.book_id = bg.book_id
        JOIN books.genres g ON bg.genre_id = g.genre_id
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.language = :language
          AND (g.slug ILIKE :query_pattern OR g.name ILIKE :query_pattern)
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url,
                 b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
                 b.created_at, s.slug
        ORDER BY
            COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) DESC,
            COALESCE(b.avg_rating, 0) DESC,
            b.created_at DESC
        LIMIT :limit OFFSET :offset
    """
    )

    result = await session.execute(
        books_query,
        {
            "language": language,
            "query_pattern": f"%{query}%",
            "limit": limit,
            "offset": offset,
        },
    )

    books = []
    for row in result:
        books.append(
            {
                "type": "book",
                "id": row.book_id,
                "title": row.title,
                "slug": row.slug,
                "cover_url": row.primary_cover_url or "",
                "authors": row.authors_names or [],
                "relevance_score": 1.0,
                "author_slugs": row.author_slugs or [],
                "series_slug": row.series_slug or "",
                "app_avg_rating": (
                    float(row.app_avg_rating) if row.app_avg_rating else None
                ),
                "app_rating_count": row.app_rating_count,
                "ol_avg_rating": (
                    float(row.ol_avg_rating) if row.ol_avg_rating else None
                ),
                "ol_rating_count": row.ol_rating_count,
                "readers": row.readers or 0,
                "book_count": 0,
                "language": language,
            }
        )

    return books, total


async def _get_author_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    limit: int,
    language: str,
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = sqlalchemy.text(
        """
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            COALESCE(b.rating_count, 0) as app_rating_count,
            b.avg_rating as app_avg_rating,
            COALESCE(b.ol_rating_count, 0) as ol_rating_count,
            b.ol_avg_rating,
            b.ol_want_to_read_count + b.ol_currently_reading_count
                + b.ol_already_read_count
                + (SELECT COUNT(*) FROM user_data.bookshelves bsh
                   WHERE bsh.book_id = b.book_id
                     AND bsh.status != 'abandoned') AS readers,
            ARRAY_AGG(a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE ba.author_id = :author_id AND b.language = :language
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating, b.created_at, s.slug
        ORDER BY
            COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) DESC,
            COALESCE(b.avg_rating, 0) DESC,
            b.created_at DESC
        LIMIT :limit
    """
    )

    result = await session.execute(
        query, {"author_id": author_id, "limit": limit, "language": language}
    )

    books = []
    for row in result:
        books.append(
            {
                "type": "book",
                "id": row.book_id,
                "title": row.title,
                "slug": row.slug,
                "cover_url": row.primary_cover_url or "",
                "authors": row.authors_names or [],
                "relevance_score": 0.4,
                "author_slugs": row.author_slugs or [],
                "series_slug": row.series_slug or "",
                "app_avg_rating": (
                    float(row.app_avg_rating) if row.app_avg_rating else None
                ),
                "app_rating_count": row.app_rating_count,
                "ol_avg_rating": (
                    float(row.ol_avg_rating) if row.ol_avg_rating else None
                ),
                "ol_rating_count": row.ol_rating_count,
                "readers": row.readers or 0,
                "book_count": 0,
                "language": language,
            }
        )

    return books


async def _get_series_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    limit: int,
    language: str,
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = sqlalchemy.text(
        """
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.primary_cover_url,
            b.series_position,
            COALESCE(b.rating_count, 0) as app_rating_count,
            b.avg_rating as app_avg_rating,
            COALESCE(b.ol_rating_count, 0) as ol_rating_count,
            b.ol_avg_rating,
            b.ol_want_to_read_count + b.ol_currently_reading_count
                + b.ol_already_read_count
                + (SELECT COUNT(*) FROM user_data.bookshelves bsh
                   WHERE bsh.book_id = b.book_id
                     AND bsh.status != 'abandoned') AS readers,
            ARRAY_AGG(a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.series_id = :series_id AND b.language = :language
        GROUP BY b.book_id, b.title, b.slug, b.primary_cover_url, b.series_position, b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating, b.created_at, s.slug
        ORDER BY
            b.series_position ASC NULLS LAST,
            b.created_at ASC
        LIMIT :limit
    """
    )

    result = await session.execute(
        query, {"series_id": series_id, "limit": limit, "language": language}
    )

    books = []
    for row in result:
        books.append(
            {
                "type": "book",
                "id": row.book_id,
                "title": row.title,
                "slug": row.slug,
                "cover_url": row.primary_cover_url or "",
                "authors": row.authors_names or [],
                "relevance_score": 0.4,
                "author_slugs": row.author_slugs or [],
                "series_slug": row.series_slug or "",
                "app_avg_rating": (
                    float(row.app_avg_rating) if row.app_avg_rating else None
                ),
                "app_rating_count": row.app_rating_count,
                "ol_avg_rating": (
                    float(row.ol_avg_rating) if row.ol_avg_rating else None
                ),
                "ol_rating_count": row.ol_rating_count,
                "readers": row.readers or 0,
                "book_count": 0,
                "language": language,
            }
        )

    return books
