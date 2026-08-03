import asyncio
import dataclasses
import logging
import typing

import app.cache
import app.config
import app.es_client
import app.services._language_boost
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_TYPE_TO_KIND: typing.Dict[str, str] = {
    "books": "book",
    "authors": "author",
    "series": "series",
}

# Fixed dropdown composition for the app-bar typeahead: books lead, but
# authors and series always get their own slots so a title match can never
# crowd them out entirely (the failure the previous single-list-then-cut
# suggest had — a query could return books only, no author, no series).
_SUGGEST_BUCKETS: typing.Tuple[typing.Tuple[str, int], ...] = (
    ("book", 5),
    ("author", 3),
    ("series", 3),
)


@dataclasses.dataclass(frozen=True)
class SearchProfile:
    """Ranking behavior for one surface.

    Suggest (the app-bar dropdown) and the search page share the same text
    tiers and the same popularity/quality signal, combined multiplicatively
    (see `_build_rescore`), but disagree on two things: whether the loose
    recall tier runs at all, and how sharply popularity should separate a
    well-known title from an obscure one with a similar text match — that's
    `popularity_pivot`, not a scalar weight. A uniform weight on top of a
    *multiplicative* combination would scale every candidate's score by the
    same factor and cancel out under sorting; the pivot instead reshapes the
    saturation curve itself, which is what actually changes relative order.
    Suggest uses a much higher pivot so the gap between a handful of readers
    and a six-figure readership stays wide instead of both saturating near 1.0.
    """

    recall: bool
    popularity_pivot: float


def _search_profile() -> SearchProfile:
    settings = app.config.settings
    return SearchProfile(recall=True, popularity_pivot=settings.search_popularity_pivot)


def _suggest_profile() -> SearchProfile:
    settings = app.config.settings
    return SearchProfile(recall=False, popularity_pivot=settings.suggest_popularity_pivot)


def _localized_fields(base: str) -> typing.List[str]:
    return [
        app.es_client.language_field(base, language)
        for language in app.es_client.stemmed_languages()
    ]


def _exact_clause(query: str) -> typing.Dict[str, typing.Any]:
    # `name.exact` is a keyword field with a folded normalizer, which Elasticsearch
    # applies to the query value automatically — no manual case/diacritic folding
    # needed here, unlike a `prefix`/`wildcard` query against an analyzed field.
    return {"term": {"name.exact": {"value": query, "boost": 30.0}}}


def _prefix_clause(query: str) -> typing.Dict[str, typing.Any]:
    fields = ["name.prefix^6"] + [f"{field}.prefix^7" for field in _localized_fields("name")]
    fields += ["alt_names.prefix^2", "authors_names.prefix^3"]
    return {
        "multi_match": {
            "query": query,
            "fields": fields,
            "type": "best_fields",
        }
    }


def _phrase_clauses(query: str) -> typing.List[typing.Dict[str, typing.Any]]:
    clauses = [{"match_phrase": {"name": {"query": query, "slop": 1, "boost": 10.0}}}]
    clauses.extend(
        {"match_phrase": {field: {"query": query, "slop": 1, "boost": 12.0}}}
        for field in _localized_fields("name")
    )
    return clauses


def _recall_fields() -> typing.List[str]:
    return (
        ["name^5"]
        + [f"{field}^6" for field in _localized_fields("name")]
        + ["alt_names^2", "authors_names^3", "series_name^2"]
    )


def _recall_clause(query: str) -> typing.Dict[str, typing.Any]:
    return {
        "multi_match": {
            "query": query,
            "fields": _recall_fields(),
            "type": "best_fields",
            "minimum_should_match": "2<75%",
        }
    }


def _fuzzy_clause(query: str) -> typing.Dict[str, typing.Any]:
    return {
        "multi_match": {
            "query": query,
            "fields": _recall_fields(),
            "type": "best_fields",
            "fuzziness": "AUTO",
            "prefix_length": 2,
            "max_expansions": 20,
        }
    }


def _build_text_queries(
    query: str, profile: SearchProfile, fuzzy: bool
) -> typing.List[typing.Dict[str, typing.Any]]:
    clauses = [_exact_clause(query), _prefix_clause(query)]
    clauses.extend(_phrase_clauses(query))
    if profile.recall:
        clauses.append(_recall_clause(query))
    if fuzzy:
        clauses.append(_fuzzy_clause(query))
    return clauses


def _build_query(
    query: str,
    profile: SearchProfile,
    kind: typing.Optional[str],
    fuzzy: bool = False,
) -> typing.Dict[str, typing.Any]:
    # `dis_max` takes the best-matching tier plus a small share of the rest,
    # so the text score stays in a tight, predictable range instead of the
    # unbounded sum a `bool.should` of a dozen clauses produces — which is
    # what let popularity's `rescore` weight actually matter, and what
    # `min_score` can be set meaningfully against.
    bool_query: typing.Dict[str, typing.Any] = {
        "must": [
            {"dis_max": {"queries": _build_text_queries(query, profile, fuzzy), "tie_breaker": 0.1}}
        ],
    }
    if kind:
        bool_query["filter"] = [{"term": {"kind": kind}}]
    return {"bool": bool_query}


def _signal_clauses(language: str, popularity_pivot: float) -> typing.List[typing.Dict[str, typing.Any]]:
    """Popularity, quality and a light nudge toward languages the reader reads.

    The query text already says which language the reader wants — someone
    typing an English title wants that book, not the translation that happens
    to match their interface language — so language is a tie-break between
    otherwise equal matches, not a ranking force.
    """
    settings = app.config.settings

    return [
        {
            "rank_feature": {
                "field": "popularity",
                "saturation": {"pivot": popularity_pivot},
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


def _build_rescore(language: str, profile: SearchProfile) -> typing.Dict[str, typing.Any]:
    # `score_mode: multiply` makes the signal a real proportional multiplier
    # over the text score, regardless of that score's absolute magnitude — a
    # necessity on a corpus this size, where `dis_max`/BM25 scores commonly
    # run in the hundreds of thousands and would swallow any additive rank
    # feature (max ~2.3) without ever moving the ranking.
    return {
        "window_size": 100,
        "query": {
            "rescore_query": {"bool": {"should": _signal_clauses(language, profile.popularity_pivot)}},
            "score_mode": "multiply",
        },
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


def _work_result(
    source: typing.Dict[str, typing.Any], score: float, language: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
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
        "relevance_score": float(score or 0),
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


def _author_result(source: typing.Dict[str, typing.Any], score: float) -> typing.Dict[str, typing.Any]:
    return {
        "type": "author",
        "id": source["author_id"],
        "title": source.get("name") or "",
        "slug": source.get("slug") or "",
        "work_id": "",
        "cover_url": source.get("photo_url") or "",
        "authors": [],
        "relevance_score": float(score or 0),
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


def _series_result(
    source: typing.Dict[str, typing.Any], score: float, language: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
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
        "relevance_score": float(score or 0),
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


def _hit_to_result(
    hit: typing.Dict[str, typing.Any], language: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    source = hit["_source"]
    score = hit["_score"]
    kind = source.get("kind")

    if kind == "book":
        return _work_result(source, score, language)
    if kind == "author":
        return _author_result(source, score)
    if kind == "series":
        return _series_result(source, score, language)
    return None


_SOURCE_FIELDS = [
    "kind",
    "work_id",
    "author_id",
    "slug",
    "name",
    "authors_names",
    "author_slugs",
    "editions",
    "rows",
    "photo_url",
    "book_count",
    "app_avg_rating",
    "app_rating_count",
    "ol_avg_rating",
    "ol_rating_count",
    "readers",
]


async def _run_search(
    query_body: typing.Dict[str, typing.Any],
    rescore: typing.Dict[str, typing.Any],
    from_: int,
    size: int,
    language: str,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    es = app.es_client.get_es()
    response = await es.search(
        index=app.config.settings.es_index_catalog,
        query=query_body,
        rescore=rescore,
        from_=from_,
        size=size,
        source=_SOURCE_FIELDS,
        track_total_hits=True,
    )

    results = []
    for hit in response["hits"]["hits"]:
        result = _hit_to_result(hit, language)
        if result is not None:
            results.append(result)

    return results, response["hits"]["total"]["value"]


async def _search_catalog(
    query: str,
    profile: SearchProfile,
    language: str,
    kind: typing.Optional[str],
    offset: int,
    limit: int,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    rescore = _build_rescore(language, profile)

    body = _build_query(query, profile, kind, fuzzy=False)
    results, total = await _run_search(body, rescore, offset, limit, language)

    # A typo'd query returning nothing is worse than a fuzzy guess.
    if total == 0:
        fuzzy_body = _build_query(query, profile, kind, fuzzy=True)
        results, total = await _run_search(fuzzy_body, rescore, offset, limit, language)

    return results, total


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

    kind = _TYPE_TO_KIND.get(type_filter)
    profile = _search_profile()
    results, total = await _search_catalog(query, profile, language, kind, offset, limit)

    await app.cache.set_cached(
        cache_key,
        {"results": results, "total": total},
        app.config.settings.cache_search_ttl,
    )

    return results, total


async def _fetch_suggest_buckets(
    query: str, profile: SearchProfile, language: str, fuzzy: bool
) -> typing.Dict[str, typing.List[typing.Dict[str, typing.Any]]]:
    rescore = _build_rescore(language, profile)

    async def _fetch(kind: str, cap: int) -> typing.List[typing.Dict[str, typing.Any]]:
        body = _build_query(query, profile, kind, fuzzy=fuzzy)
        results, _total = await _run_search(body, rescore, 0, cap, language)
        return results

    fetched = await asyncio.gather(*(_fetch(kind, cap) for kind, cap in _SUGGEST_BUCKETS))
    return {kind: results for (kind, _cap), results in zip(_SUGGEST_BUCKETS, fetched)}


async def suggest(
    query: str,
    limit: int = 8,
    language: str = "en",
) -> typing.List[typing.Dict[str, typing.Any]]:
    cache_key = f"suggest:{query}:{limit}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached

    profile = _suggest_profile()
    # Each kind is fetched with its own kind-filtered query rather than one
    # mixed query cut to size — a shared top-N window lets a landslide of book
    # matches crowd authors and series out of the results entirely, which is
    # exactly the dropdown-with-no-authors bug this replaces.
    buckets = await _fetch_suggest_buckets(query, profile, language, fuzzy=False)

    if not any(buckets.values()):
        buckets = await _fetch_suggest_buckets(query, profile, language, fuzzy=True)

    results: typing.List[typing.Dict[str, typing.Any]] = []
    for kind, cap in _SUGGEST_BUCKETS:
        results.extend(buckets[kind][:cap])
    results = results[:limit]

    await app.cache.set_cached(cache_key, results, 60)
    return results


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
        {app.services._language_boost.work_shelf_counts_join()}
        WHERE {app.services._language_boost.preferred_edition_sql(require_cover=False)}
          AND (g.slug ILIKE :query_pattern OR g.name ILIKE :query_pattern)
        GROUP BY b.book_id, b.title, b.slug, b.work_id, b.language, b.primary_cover_url,
                 b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
                 b.created_at, s.slug, wsc.readers
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
