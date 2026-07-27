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

# Merged pages are cut from a single ordered stream, so each type has to be
# fetched deep enough to cover the requested window. Capped because a deep
# window costs the same on every shard.
MAX_FETCH_SIZE = 200


def _normalize_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKD", query)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def _normalize_scores(
    results: typing.List[typing.Dict[str, typing.Any]], type_weight: float
) -> typing.List[typing.Dict[str, typing.Any]]:
    if not results:
        return results
    max_score = max(r["relevance_score"] for r in results) or 1.0
    for r in results:
        r["relevance_score"] = (r["relevance_score"] / max_score) * type_weight
    return results


class TextFields:
    """Which fields a query runs against, for one index.

    `base` carries every language's text under the language-agnostic analyzer;
    `localized` is the per-language stemmed copy of the same values. Cross-field
    matching groups fields by analyzer, so only same-analyzer fields (`base`
    plus the other generic ones) may share a `cross_fields` clause.
    """

    def __init__(
        self,
        base: str,
        companions: typing.Optional[typing.Sequence[typing.Tuple[str, float]]] = None,
    ) -> None:
        self.base = base
        self.companions = list(companions or [])

    def localized(self) -> typing.List[str]:
        return [
            app.es_client.language_field(self.base, language)
            for language in app.es_client.stemmed_languages()
        ]

    def best_fields(self) -> typing.List[str]:
        return (
            [f"{self.base}^4"]
            + [f"{field}^5" for field in self.localized()]
            + [f"{field}^{boost}" for field, boost in self.companions]
        )

    def generic_fields(self) -> typing.List[str]:
        return [f"{self.base}^3"] + [
            f"{field}^{boost}" for field, boost in self.companions
        ]

    def phrase_fields(self) -> typing.List[typing.Tuple[str, float]]:
        return (
            [(self.base, 6.0)]
            + [(field, 7.0) for field in self.localized()]
            + [(field, boost) for field, boost in self.companions]
        )

    def suggest_fields(self) -> typing.List[str]:
        fields = [
            f"{self.base}.suggest^3",
            f"{self.base}.suggest._2gram",
            f"{self.base}.suggest._3gram",
        ]
        for field, boost in self.companions:
            if field == "series_name":
                continue
            fields.extend(
                [
                    f"{field}.suggest^{boost}",
                    f"{field}.suggest._2gram",
                    f"{field}.suggest._3gram",
                ]
            )

        return fields


_WORK_FIELDS = TextFields("titles", [("authors_names", 3.0), ("series_name", 2.0)])
_AUTHOR_FIELDS = TextFields("name")
_SERIES_FIELDS = TextFields("names")


def _text_clauses(
    query: str, fields: TextFields, fuzzy: bool
) -> typing.List[typing.Dict[str, typing.Any]]:
    clauses: typing.List[typing.Dict[str, typing.Any]] = [
        # Whole-value match on the folded copy: case- and diacritic-insensitive
        # without asking the reader to reproduce "Władca" exactly.
        {"match": {f"{fields.base}.folded": {"query": query, "boost": 12.0}}},
        {
            "multi_match": {
                "query": query,
                "fields": fields.best_fields(),
                "type": "best_fields",
                "tie_breaker": 0.3,
            }
        },
        {
            "multi_match": {
                "query": query,
                "fields": fields.generic_fields(),
                "type": "cross_fields",
                "operator": "and",
            }
        },
    ]
    clauses.extend(
        {"match_phrase": {field: {"query": query, "slop": 1, "boost": boost}}}
        for field, boost in fields.phrase_fields()
    )

    if fuzzy:
        clauses.append(
            {
                "multi_match": {
                    "query": query,
                    "fields": fields.best_fields(),
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                    "boost": 0.5,
                }
            }
        )

    return clauses


def _signal_clauses(language: str) -> typing.List[typing.Dict[str, typing.Any]]:
    """Popularity, quality and a light nudge toward languages the reader reads.

    Deliberately additive and small. The query text already says which language
    the reader wants — someone typing an English title wants that book, not the
    translation that happens to match their interface language — so language is
    a tie-break between otherwise equal matches, not a ranking force.
    """
    settings = app.config.settings

    return [
        {
            "rank_feature": {
                "field": "popularity",
                "saturation": {"pivot": settings.search_popularity_pivot},
                "boost": settings.search_popularity_boost,
            }
        },
        {
            "rank_feature": {
                "field": "quality",
                "saturation": {"pivot": settings.search_quality_pivot},
                "boost": settings.search_quality_boost,
            }
        },
        {
            "terms": {
                "languages": [language],
                "boost": settings.search_language_boost,
            }
        },
    ]


def _build_query(
    query: str, fields: TextFields, language: str, fuzzy: bool = True
) -> typing.Dict[str, typing.Any]:
    # Text match is the gate (`must`); signals only reorder what already
    # matched. A signal in a top-level `should` with `minimum_should_match: 1`
    # would let popular documents in on no textual match at all.
    return {
        "bool": {
            "must": [
                {
                    "bool": {
                        "should": _text_clauses(query, fields, fuzzy),
                        "minimum_should_match": 1,
                    }
                }
            ],
            "should": _signal_clauses(language),
        }
    }


def _build_suggest_query(
    query: str,
    fields: TextFields,
    language: str,
    fuzziness: typing.Optional[str] = None,
) -> typing.Dict[str, typing.Any]:
    suggest_clause: typing.Dict[str, typing.Any] = {
        "query": query,
        "type": "bool_prefix",
        "fields": fields.suggest_fields(),
    }
    if fuzziness:
        suggest_clause["fuzziness"] = fuzziness

    text_clauses: typing.List[typing.Dict[str, typing.Any]] = [
        {"prefix": {f"{fields.base}.folded": {"value": _normalize_query(query), "boost": 4.0}}},
        {"multi_match": suggest_clause},
    ]

    return {
        "bool": {
            "must": [{"bool": {"should": text_clauses, "minimum_should_match": 1}}],
            "should": _signal_clauses(language),
        }
    }


def select_edition(
    editions: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.Dict[str, typing.Any]:
    """The edition a reader in `language` should be shown: theirs, English, best.

    Same order the book page falls back in, so a search result and the page it
    links to agree on which edition the reader is looking at.
    """
    for candidate_language in (language, "en"):
        for edition in editions:
            if edition.get("language") == candidate_language:
                return edition

    return max(editions, key=lambda edition: edition.get("ratings") or 0)


def _select_series_row(
    rows: typing.List[typing.Dict[str, typing.Any]], language: str
) -> typing.Dict[str, typing.Any]:
    for candidate_language in (language, "en"):
        for row in rows:
            if row.get("language") == candidate_language:
                return row

    return max(rows, key=lambda row: row.get("book_count") or 0)


def _work_hit_to_result(
    hit: typing.Dict[str, typing.Any], language: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    source = hit["_source"]
    editions = source.get("editions") or []
    if not editions:
        return None

    edition = select_edition(editions, language)

    return {
        "type": "book",
        "id": edition["book_id"],
        "title": edition.get("title") or "",
        "slug": edition.get("slug") or "",
        "work_id": source.get("work_id") or "",
        "cover_url": edition.get("cover_url") or "",
        "authors": list(source.get("authors_names") or []),
        "relevance_score": float(hit["_score"] or 0),
        "author_slugs": list(source.get("author_slugs") or []),
        "series_slug": edition.get("series_slug") or "",
        "app_avg_rating": source.get("app_avg_rating"),
        "app_rating_count": source.get("app_rating_count") or 0,
        "ol_avg_rating": source.get("ol_avg_rating"),
        "ol_rating_count": source.get("ol_rating_count") or 0,
        "readers": source.get("readers") or 0,
        "book_count": 0,
        "language": edition.get("language") or "",
    }


def _author_hit_to_result(
    hit: typing.Dict[str, typing.Any], _language: str
) -> typing.Dict[str, typing.Any]:
    source = hit["_source"]

    return {
        "type": "author",
        "id": source["author_id"],
        "title": source.get("name") or "",
        "slug": source.get("slug") or "",
        "work_id": "",
        "cover_url": source.get("photo_url") or "",
        "authors": [],
        "relevance_score": float(hit["_score"] or 0),
        "author_slugs": [],
        "series_slug": "",
        "app_avg_rating": source.get("app_avg_rating"),
        "app_rating_count": source.get("app_rating_count") or 0,
        "ol_avg_rating": source.get("ol_avg_rating"),
        "ol_rating_count": source.get("ol_rating_count") or 0,
        "readers": source.get("readers") or 0,
        "book_count": source.get("book_count") or 0,
        "language": "",
    }


def _series_hit_to_result(
    hit: typing.Dict[str, typing.Any], language: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    source = hit["_source"]
    rows = source.get("rows") or []
    if not rows:
        return None

    row = _select_series_row(rows, language)

    return {
        "type": "series",
        "id": row["series_id"],
        "title": row.get("name") or "",
        "slug": source.get("slug") or "",
        "work_id": "",
        "cover_url": "",
        "authors": [],
        "relevance_score": float(hit["_score"] or 0),
        "author_slugs": [],
        "series_slug": "",
        "app_avg_rating": source.get("app_avg_rating"),
        "app_rating_count": source.get("app_rating_count") or 0,
        "ol_avg_rating": source.get("ol_avg_rating"),
        "ol_rating_count": source.get("ol_rating_count") or 0,
        "readers": source.get("readers") or 0,
        "book_count": row.get("book_count") or 0,
        "language": row.get("language") or "",
    }


_WORK_SOURCE_FIELDS = [
    "work_id",
    "authors_names",
    "author_slugs",
    "editions",
    "app_avg_rating",
    "app_rating_count",
    "ol_avg_rating",
    "ol_rating_count",
    "readers",
]
_AUTHOR_SOURCE_FIELDS = [
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
]
_SERIES_SOURCE_FIELDS = [
    "slug",
    "rows",
    "app_avg_rating",
    "app_rating_count",
    "ol_avg_rating",
    "ol_rating_count",
    "readers",
]


async def _run_search(
    index: str,
    query_body: typing.Dict[str, typing.Any],
    size: int,
    source_fields: typing.List[str],
    to_result: typing.Callable[
        [typing.Dict[str, typing.Any], str], typing.Optional[typing.Dict[str, typing.Any]]
    ],
    language: str,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    response = await es.search(
        index=index,
        query=query_body,
        from_=0,
        size=size,
        source=source_fields,
        track_total_hits=True,
    )

    results = []
    for hit in response["hits"]["hits"]:
        result = to_result(hit, language)
        if result is not None:
            results.append(result)

    return results, response["hits"]["total"]["value"]


async def _search_works_es(
    query: str, size: int, language: str
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    return await _run_search(
        app.config.settings.es_index_books,
        _build_query(query, _WORK_FIELDS, language),
        size,
        _WORK_SOURCE_FIELDS,
        _work_hit_to_result,
        language,
    )


async def _search_authors_es(
    query: str, size: int, language: str
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    return await _run_search(
        app.config.settings.es_index_authors,
        _build_query(query, _AUTHOR_FIELDS, language),
        size,
        _AUTHOR_SOURCE_FIELDS,
        _author_hit_to_result,
        language,
    )


async def _search_series_es(
    query: str, size: int, language: str
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    return await _run_search(
        app.config.settings.es_index_series,
        _build_query(query, _SERIES_FIELDS, language),
        size,
        _SERIES_SOURCE_FIELDS,
        _series_hit_to_result,
        language,
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

    # Category search is a genre lookup in Postgres, already windowed there.
    if type_filter == "categories":
        category_results, category_total = await _search_books_by_category(
            session, query, limit, offset, language
        )
        await app.cache.set_cached(
            cache_key,
            {"results": category_results, "total": category_total},
            app.config.settings.cache_search_ttl,
        )

        return category_results, category_total

    # Each type is fetched to the end of the requested window rather than one
    # page deep: the types are merged into a single ranking, so a result that
    # loses the race on page 1 still has to be available to land on page 2.
    fetch_size = min(offset + limit, MAX_FETCH_SIZE)

    results: typing.List[typing.Dict[str, typing.Any]] = []
    total_count = 0
    author_results: typing.List[typing.Dict[str, typing.Any]] = []
    series_results: typing.List[typing.Dict[str, typing.Any]] = []

    if type_filter in ["all", "books"]:
        book_results, book_total = await _search_works_es(query, fetch_size, language)
        results.extend(_normalize_scores(book_results, 1.0))
        total_count += book_total

    if type_filter in ["all", "authors"]:
        author_results, author_total = await _search_authors_es(
            query, fetch_size, language
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
            query, fetch_size, language
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

    # Expansions can repeat a work the main query already returned, and the
    # index itself holds one document per work, so this only collapses overlap
    # between the two sources.
    results = app.services._language_boost.dedupe_by_work(results, language)
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    final_results = results[offset : offset + limit]

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
    settings = app.config.settings

    books_results, _ = await _run_search(
        settings.es_index_books,
        _build_suggest_query(query, _WORK_FIELDS, language, fuzziness),
        limit,
        _WORK_SOURCE_FIELDS,
        _work_hit_to_result,
        language,
    )
    authors_results, _ = await _run_search(
        settings.es_index_authors,
        _build_suggest_query(query, _AUTHOR_FIELDS, language, fuzziness),
        limit,
        _AUTHOR_SOURCE_FIELDS,
        _author_hit_to_result,
        language,
    )
    series_results, _ = await _run_search(
        settings.es_index_series,
        _build_suggest_query(query, _SERIES_FIELDS, language, fuzziness),
        limit,
        _SERIES_SOURCE_FIELDS,
        _series_hit_to_result,
        language,
    )

    merged = (
        _normalize_scores(books_results, 1.0)
        + _normalize_scores(authors_results, 0.95)
        + _normalize_scores(series_results, 0.9)
    )
    merged.sort(key=lambda x: x["relevance_score"], reverse=True)

    return merged[:limit]


async def _search_books_by_category(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int,
    offset: int,
    language: str,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    count_query = sqlalchemy.text(
        """
        SELECT COUNT(DISTINCT b.work_id)
        FROM books.books b
        JOIN books.book_genres bg ON b.book_id = bg.book_id
        JOIN books.genres g ON bg.genre_id = g.genre_id
        WHERE (g.slug ILIKE :query_pattern OR g.name ILIKE :query_pattern)
    """
    )

    count_result = await session.execute(
        count_query,
        {"query_pattern": f"%{query}%"},
    )
    total = count_result.scalar() or 0

    books_query = sqlalchemy.text(
        f"""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.work_id,
            b.language,
            b.primary_cover_url,
            COALESCE(b.rating_count, 0) as app_rating_count,
            b.avg_rating as app_avg_rating,
            COALESCE(b.ol_rating_count, 0) as ol_rating_count,
            b.ol_avg_rating,
            {app.services._language_boost.work_readers_sql()} AS readers,
            ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        JOIN books.book_genres bg ON b.book_id = bg.book_id
        JOIN books.genres g ON bg.genre_id = g.genre_id
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE {app.services._language_boost.preferred_edition_sql(require_cover=False)}
          AND (g.slug ILIKE :query_pattern OR g.name ILIKE :query_pattern)
        GROUP BY b.book_id, b.title, b.slug, b.work_id, b.language, b.primary_cover_url,
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
                "work_id": row.work_id or "",
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
                "language": row.language or language,
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
        f"""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.work_id,
            b.language,
            b.primary_cover_url,
            COALESCE(b.rating_count, 0) as app_rating_count,
            b.avg_rating as app_avg_rating,
            COALESCE(b.ol_rating_count, 0) as ol_rating_count,
            b.ol_avg_rating,
            {app.services._language_boost.work_readers_sql()} AS readers,
            ARRAY_AGG(a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE ba.author_id = :author_id AND {app.services._language_boost.preferred_edition_sql(require_cover=False)}
        GROUP BY b.book_id, b.title, b.slug, b.work_id, b.language, b.primary_cover_url, b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating, b.created_at, s.slug
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

    return [_expansion_row_to_result(row, language) for row in result]


async def _get_series_top_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_id: int,
    limit: int,
    language: str,
) -> typing.List[typing.Dict[str, typing.Any]]:
    query = sqlalchemy.text(
        f"""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.work_id,
            b.language,
            b.primary_cover_url,
            b.series_position,
            COALESCE(b.rating_count, 0) as app_rating_count,
            b.avg_rating as app_avg_rating,
            COALESCE(b.ol_rating_count, 0) as ol_rating_count,
            b.ol_avg_rating,
            {app.services._language_boost.work_readers_sql()} AS readers,
            ARRAY_AGG(a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
            ARRAY_AGG(a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
            s.slug as series_slug
        FROM books.books b
        LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
        LEFT JOIN books.authors a ON ba.author_id = a.author_id
        LEFT JOIN books.series s ON b.series_id = s.series_id
        WHERE b.series_id = :series_id AND {app.services._language_boost.preferred_edition_sql(require_cover=False)}
        GROUP BY b.book_id, b.title, b.slug, b.work_id, b.language, b.primary_cover_url, b.series_position, b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating, b.created_at, s.slug
        ORDER BY
            b.series_position ASC NULLS LAST,
            b.created_at ASC
        LIMIT :limit
    """
    )

    result = await session.execute(
        query, {"series_id": series_id, "limit": limit, "language": language}
    )

    return [_expansion_row_to_result(row, language) for row in result]


def _expansion_row_to_result(
    row: typing.Any, language: str
) -> typing.Dict[str, typing.Any]:
    return {
        "type": "book",
        "id": row.book_id,
        "title": row.title,
        "slug": row.slug,
        "work_id": row.work_id or "",
        "cover_url": row.primary_cover_url or "",
        "authors": row.authors_names or [],
        "relevance_score": 0.4,
        "author_slugs": row.author_slugs or [],
        "series_slug": row.series_slug or "",
        "app_avg_rating": float(row.app_avg_rating) if row.app_avg_rating else None,
        "app_rating_count": row.app_rating_count,
        "ol_avg_rating": float(row.ol_avg_rating) if row.ol_avg_rating else None,
        "ol_rating_count": row.ol_rating_count,
        "readers": row.readers or 0,
        "book_count": 0,
        "language": row.language or language,
    }
