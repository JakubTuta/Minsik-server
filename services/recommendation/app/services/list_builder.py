import asyncio
import logging
import typing

import app.cache
import app.config
import app.services._language_boost
import app.services.author_recommender
import app.services.book_of_week_builder
import app.services.book_recommender
import app.services.series_recommender
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

# Shelf counts are pooled per work and counted per distinct user, so a book's
# popularity is the same in every language and a reader who shelved two
# translations still counts once. ol_* counts are already work-level: the dump
# pipeline writes them identically to every language row.
#
# books.work_shelf_counts is keyed by work_id, so the ranking stage below joins
# it one-to-one and reads its columns directly (the _RANK_* variants). The
# hydration stage also joins authors, which multiplies rows, so there the same
# value has to be pulled back out of the group with MAX().
_READERS_EXPR = """
    COALESCE(b.ol_want_to_read_count, 0) + COALESCE(b.ol_currently_reading_count, 0)
    + COALESCE(b.ol_already_read_count, 0) + COALESCE(MAX(wsc.readers), 0)
"""

_RANK_READERS_EXPR = """
    COALESCE(b.ol_want_to_read_count, 0) + COALESCE(b.ol_currently_reading_count, 0)
    + COALESCE(b.ol_already_read_count, 0) + COALESCE(wsc.readers, 0)
"""

_RANK_WANT_TO_READ_EXPR = (
    "COALESCE(b.ol_want_to_read_count, 0) + COALESCE(wsc.want_to_read_count, 0)"
)

_RANK_CURRENTLY_READING_EXPR = (
    "COALESCE(b.ol_currently_reading_count, 0) + COALESCE(wsc.reading_count, 0)"
)

_RATING_COUNT_EXPR = "COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)"

_WEIGHTED_RATING_EXPR = f"""
    CASE
        WHEN ({_RATING_COUNT_EXPR}) = 0 THEN 0
        ELSE (
            COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
            + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0)
        ) / ({_RATING_COUNT_EXPR})
    END
"""

_BOOK_FIELDS = f"""
    b.book_id,
    b.title,
    b.slug,
    b.work_id,
    b.language,
    b.primary_cover_url,
    CASE
        WHEN ({_RATING_COUNT_EXPR}) > 0
        THEN ROUND(
            (COALESCE(b.avg_rating::numeric, 0) * COALESCE(b.rating_count, 0)
             + COALESCE(b.ol_avg_rating::numeric, 0) * COALESCE(b.ol_rating_count, 0))
            / ({_RATING_COUNT_EXPR}), 2
        )::text
        ELSE ''
    END AS avg_rating,
    {_RATING_COUNT_EXPR} AS rating_count,
    ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) AS author_names,
    ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) AS author_slugs,
    {_READERS_EXPR} AS readers
"""

# The shelf counts come from books.work_shelf_counts (refreshed on a cron by the
# books service) rather than a lateral aggregate over user_data.bookshelves:
# that lateral ran once per candidate book, so a 40-row list re-aggregated the
# shelf table hundreds of thousands of times.
_BOOK_JOINS = """
    LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
    LEFT JOIN books.authors a ON ba.author_id = a.author_id
    LEFT JOIN books.work_shelf_counts wsc ON wsc.work_id = b.work_id
"""

# For a query that already narrows to a handful of books (one series, one
# author, a list of ids) the per-row edition subquery is cheap.
_BOOK_BASE_WHERE = (
    "b.primary_cover_url IS NOT NULL AND "
    + app.services._language_boost.preferred_edition_sql()
)

# For a query whose candidates are the whole catalog it is not: it re-ran the
# subquery once per book. This elects the same edition in a single sort, and is
# what every catalog-wide list below drives off.
#
# It yields ids rather than whole rows so the outer query still reads columns
# from books.books itself, which is what lets `GROUP BY b.book_id` stand in for
# grouping by every selected column.
CANONICAL_BOOKS_CTE = """
    canonical_books AS (
        SELECT DISTINCT ON (work_id) book_id
        FROM books.books
        WHERE primary_cover_url IS NOT NULL
        ORDER BY work_id, (language = :language) DESC, (language = 'en') DESC, book_id ASC
    )
"""

_BOOK_GROUP_BY = "GROUP BY b.book_id"


def hydrate_books_from(
    ranked_cte: str = "ranked", order_sql: str = "score DESC NULLS LAST"
) -> str:
    """Attach authors and shelf counts to an already-ranked, already-cut row set.

    The author join multiplies rows and both ARRAY_AGGs sort within each group,
    so this must never run over a candidate set the query has not yet narrowed
    to the rows it will return. `ranked_cte` must expose `book_id` and `score`.
    """
    return f"""
        SELECT {_BOOK_FIELDS}, r.score AS score
        FROM {ranked_cte} r
        JOIN books.books b ON b.book_id = r.book_id
        {_BOOK_JOINS}
        {_BOOK_GROUP_BY}, r.score
        ORDER BY {order_sql}
    """


def _catalog_list_query(
    score_sql: str,
    where_sql: str = "",
    order_sql: str = "score DESC NULLS LAST",
    extra_cte: str = "",
    rank_joins: str = "",
    rank_group_by: str = "",
) -> str:
    """Rank the whole catalog on the lean row, then hydrate the survivors only.

    Every list below scores the catalog and keeps `limit` rows. Joining authors
    before that cut meant two `ARRAY_AGG(DISTINCT ...)` — each a per-group sort
    — ran for every book in the catalog so a hundred of them could survive it,
    the same shape that made the case pool refresh exhaust Postgres. Ranking
    reads books.books and the work_shelf_counts rollup only, so the expensive
    join and aggregation happen against `limit` rows instead of the catalog.

    `order_sql` is applied in both stages and so may only reference the `score`
    alias and columns of `b`, which the outer `GROUP BY b.book_id` leaves
    functionally dependent and therefore selectable.
    """
    where_clause = f"WHERE {where_sql}" if where_sql else ""
    group_by_clause = f"GROUP BY {rank_group_by}" if rank_group_by else ""

    ranked_cte = f"""
        ranked AS (
            SELECT b.book_id, ({score_sql}) AS score
            FROM canonical_books cb
            JOIN books.books b ON b.book_id = cb.book_id
            LEFT JOIN books.work_shelf_counts wsc ON wsc.work_id = b.work_id
            {rank_joins}
            {where_clause}
            {group_by_clause}
            ORDER BY {order_sql}
            LIMIT :limit
        )
    """
    ctes = [CANONICAL_BOOKS_CTE]
    if extra_cte:
        ctes.append(extra_cte)
    ctes.append(ranked_cte)

    return f"WITH {','.join(ctes)}\n{hydrate_books_from(order_sql=order_sql)}"


async def _run_catalog_list(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    query: str,
    limit: int,
    language: str,
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(query), {"limit": limit, "language": language}
    )
    return [_row_to_book_item(row, float(row.score or 0)) for row in result]


def author_works_cte(author_filter: str = "") -> str:
    """One row per (author, work): the edition with the most ratings, so an
    author's translated catalog isn't summed once per language.

    `author_filter` must be supplied whenever the caller only wants a few
    authors. A join predicate in the outer query cannot be pushed into this
    CTE, so without it the whole of books.book_authors is sorted every time.
    """
    where_clause = f"WHERE {author_filter} " if author_filter else ""
    return f"""
        author_works AS (
            SELECT DISTINCT ON (ba.author_id, b.work_id)
                ba.author_id,
                b.book_id,
                b.rating_count,
                b.ol_rating_count,
                b.avg_rating,
                b.ol_avg_rating,
                b.ol_want_to_read_count,
                b.ol_currently_reading_count,
                b.ol_already_read_count
            FROM books.book_authors ba
            JOIN books.books b ON ba.book_id = b.book_id
            {where_clause}ORDER BY ba.author_id, b.work_id,
                     (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) DESC
        )
"""


def _row_to_book_item(row: typing.Any, score: float) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": row.book_id,
        "title": row.title or "",
        "slug": row.slug or "",
        "work_id": row.work_id or "",
        "language": row.language or "",
        "primary_cover_url": row.primary_cover_url or "",
        "avg_rating": row.avg_rating or "",
        "rating_count": row.rating_count or 0,
        "author_names": list(row.author_names or []),
        "author_slugs": list(row.author_slugs or []),
        "readers": int(row.readers or 0),
        "score": score,
    }


def _row_to_author_item(row: typing.Any, score: float) -> typing.Dict[str, typing.Any]:
    return {
        "author_id": row.author_id,
        "name": row.name or "",
        "slug": row.slug or "",
        "photo_url": row.photo_url or "",
        "book_count": int(row.book_count or 0),
        "avg_rating": str(row.avg_rating) if row.avg_rating else "",
        "rating_count": int(row.rating_count or 0),
        "readers": int(row.readers or 0),
        "score": score,
    }


def _make_book_section(
    section_key: str,
    display_name: str,
    items: typing.List[typing.Dict[str, typing.Any]],
    title_params: typing.Optional[typing.Dict[str, str]] = None,
) -> typing.Dict[str, typing.Any]:
    return {
        "section_key": section_key,
        "display_name": display_name,
        "item_type": "book",
        "book_items": items,
        "total": len(items),
        "title_params": title_params or {},
    }


# Shelf rows are pooled across a work's editions, so these two reach the whole
# work through its sibling editions rather than only the canonical one.
_WORK_SHELVES_JOIN = """
    JOIN books.books wb ON wb.work_id = b.work_id
    JOIN user_data.bookshelves bs ON bs.book_id = wb.book_id
"""


async def _build_most_read(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _catalog_list_query(_RANK_READERS_EXPR), limit, language
    )


async def _build_most_wanted(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _catalog_list_query(_RANK_WANT_TO_READ_EXPR), limit, language
    )


async def _build_trending_reads(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _catalog_list_query(_RANK_CURRENTLY_READING_EXPR), limit, language
    )


async def _build_most_viewed(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query(
            "COALESCE(wv.views, 0)",
            extra_cte="""
                work_views AS (
                    SELECT work_id, SUM(view_count) AS views
                    FROM books.books GROUP BY work_id
                )
            """,
            rank_joins="LEFT JOIN work_views wv ON wv.work_id = b.work_id",
        ),
        limit,
        language,
    )


async def _build_highest_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query(
            _WEIGHTED_RATING_EXPR, where_sql=f"({_RATING_COUNT_EXPR}) >= 3"
        ),
        limit,
        language,
    )


async def _build_community_top_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query("b.ol_avg_rating", where_sql="b.ol_rating_count >= 20"),
        limit,
        language,
    )


async def _build_most_rated(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _catalog_list_query(_RATING_COUNT_EXPR), limit, language
    )


async def _build_recently_added(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query(
            "EXTRACT(EPOCH FROM b.created_at)", order_sql="b.created_at DESC"
        ),
        limit,
        language,
    )


async def _build_classics(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query(
            _RANK_READERS_EXPR,
            where_sql=(
                "b.original_publication_year < 1980 "
                f"AND (({_RANK_READERS_EXPR}) >= 100 OR b.avg_rating >= 4.0)"
            ),
            order_sql="score DESC NULLS LAST, b.avg_rating DESC NULLS LAST",
        ),
        limit,
        language,
    )


async def _build_user_favorites(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query(
            "COUNT(DISTINCT bs.user_id)",
            where_sql="bs.is_favorite = true",
            rank_joins=_WORK_SHELVES_JOIN,
            rank_group_by="b.book_id",
        ),
        limit,
        language,
    )


async def _build_recently_finished(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session,
        _catalog_list_query(
            "EXTRACT(EPOCH FROM MAX(bs.updated_at))",
            where_sql="bs.status = 'read'",
            rank_joins=_WORK_SHELVES_JOIN,
            rank_group_by="b.book_id",
        ),
        limit,
        language,
    )


async def _build_currently_reading(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    # work_shelf_counts.reading_count is exactly this list's score — distinct
    # app users with the work on 'reading', pooled over its editions — so it is
    # read from the rollup instead of re-aggregating user_data.bookshelves.
    return await _run_catalog_list(
        session,
        _catalog_list_query("COALESCE(wsc.reading_count, 0)"),
        limit,
        language,
    )


def _build_sub_rating_query(dimension: str) -> str:
    return _catalog_list_query(
        f"CAST(b.sub_rating_stats->'{dimension}'->>'avg' AS FLOAT)",
        where_sql=(
            f"b.sub_rating_stats->'{dimension}'->>'count' IS NOT NULL "
            f"AND CAST(b.sub_rating_stats->'{dimension}'->>'count' AS INTEGER) >= 3"
        ),
    )


async def _build_best_writing(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _build_sub_rating_query("writing_quality"), limit, language
    )


async def _build_most_emotional(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _build_sub_rating_query("emotional_impact"), limit, language
    )


async def _build_funniest(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _build_sub_rating_query("humor"), limit, language
    )


async def _build_most_thought_provoking(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _build_sub_rating_query("intellectual_depth"), limit, language
    )


async def _build_most_rereadable(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int, language: str
) -> typing.List[typing.Dict]:
    return await _run_catalog_list(
        session, _build_sub_rating_query("rereadability"), limit, language
    )


async def _build_top_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    # The score needs no per-edition detail: ol_* reader counts are written
    # identically to every edition of a work, so a MAX per (author, work) is that
    # work's figure and summing those per author reproduces exactly what the old
    # query got from an unfiltered author_works_cte() — which sorted the whole of
    # books.book_authors joined to books.books to do it. Two narrow hash
    # aggregates settle the ranking, then author_works_cte() runs edition-accurate
    # over the `limit` authors that won.
    #
    # The aggregates are stacked rather than joined on work_id: joining a
    # per-author CTE to a per-work one is a join Postgres cannot estimate (it
    # guessed 173M rows for 48k), and the resulting cost was high enough to
    # trigger JIT compilation that cost more than the query.
    result = await session.execute(
        sqlalchemy.text(
            f"""
        WITH author_app_readers AS (
            SELECT ba_r.author_id, COUNT(DISTINCT bs_a.user_id) AS app_readers
            FROM user_data.bookshelves bs_a
            JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
            GROUP BY ba_r.author_id
        ),
        author_work_readers AS (
            SELECT ba.author_id, b.work_id, MAX(
                COALESCE(b.ol_want_to_read_count, 0)
                + COALESCE(b.ol_currently_reading_count, 0)
                + COALESCE(b.ol_already_read_count, 0)
            ) AS readers
            FROM books.book_authors ba
            JOIN books.books b ON b.book_id = ba.book_id
            GROUP BY ba.author_id, b.work_id
        ),
        top_authors AS (
            SELECT
                awr.author_id,
                COALESCE(SUM(awr.readers), 0) + COALESCE(MAX(aar.app_readers), 0) AS score
            FROM author_work_readers awr
            LEFT JOIN author_app_readers aar ON aar.author_id = awr.author_id
            GROUP BY awr.author_id
            ORDER BY score DESC
            LIMIT :limit
        ),
        {author_works_cte("ba.author_id IN (SELECT author_id FROM top_authors)")}
        SELECT
            a.author_id,
            a.name,
            a.slug,
            COALESCE(a.photo_url, '') AS photo_url,
            COUNT(DISTINCT aw.book_id) AS book_count,
            COALESCE(
                SUM(
                    COALESCE(aw.avg_rating::numeric, 0) * aw.rating_count
                    + COALESCE(aw.ol_avg_rating::numeric, 0) * aw.ol_rating_count
                )
                / NULLIF(SUM(aw.rating_count + aw.ol_rating_count), 0),
                0
            ) AS avg_rating,
            ta.score AS readers,
            COALESCE(SUM(aw.rating_count + aw.ol_rating_count), 0) AS rating_count,
            ta.score AS score
        FROM top_authors ta
        JOIN books.authors a ON a.author_id = ta.author_id
        JOIN author_works aw ON aw.author_id = a.author_id
        GROUP BY a.author_id, ta.score
        ORDER BY ta.score DESC
    """
        ),
        {"limit": limit},
    )
    return [_row_to_author_item(row, float(row.score or 0)) for row in result]


async def _build_popular_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession, limit: int
) -> typing.List[typing.Dict]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
        -- Ranked purely on view_count, so the winners are known before any
        -- stats are computed: take them first, then aggregate only those.
        WITH popular AS (
            SELECT author_id FROM books.authors
            ORDER BY view_count DESC NULLS LAST
            LIMIT :limit
        ),
        author_app_readers AS (
            SELECT ba_r.author_id, COUNT(DISTINCT bs_a.user_id) AS app_readers
            FROM user_data.bookshelves bs_a
            JOIN books.book_authors ba_r ON bs_a.book_id = ba_r.book_id
            JOIN popular p ON p.author_id = ba_r.author_id
            GROUP BY ba_r.author_id
        ),
        {author_works_cte("ba.author_id IN (SELECT author_id FROM popular)")}
        SELECT
            a.author_id,
            a.name,
            a.slug,
            COALESCE(a.photo_url, '') AS photo_url,
            COUNT(DISTINCT aw.book_id) AS book_count,
            COALESCE(
                SUM(
                    COALESCE(aw.avg_rating::numeric, 0) * aw.rating_count
                    + COALESCE(aw.ol_avg_rating::numeric, 0) * aw.ol_rating_count
                )
                / NULLIF(SUM(aw.rating_count + aw.ol_rating_count), 0),
                0
            ) AS avg_rating,
            COALESCE(SUM(
                COALESCE(aw.ol_want_to_read_count, 0) +
                COALESCE(aw.ol_currently_reading_count, 0) +
                COALESCE(aw.ol_already_read_count, 0)
            ), 0) + COALESCE(aar.app_readers, 0) AS readers,
            COALESCE(SUM(aw.rating_count + aw.ol_rating_count), 0) AS rating_count,
            COALESCE(a.view_count, 0) AS score
        FROM popular p
        JOIN books.authors a ON a.author_id = p.author_id
        LEFT JOIN author_works aw ON aw.author_id = a.author_id
        LEFT JOIN author_app_readers aar ON aar.author_id = a.author_id
        GROUP BY a.author_id, aar.app_readers
        ORDER BY a.view_count DESC NULLS LAST
    """
        ),
        {"limit": limit},
    )
    return [_row_to_author_item(row, float(row.score or 0)) for row in result]


CATEGORIES: typing.List[typing.Dict[str, typing.Any]] = [
    {
        "key": "most_read",
        "display_name": "Most Read Books",
        "item_type": "book",
        "build_fn": _build_most_read,
    },
    {
        "key": "most_wanted",
        "display_name": "Most Wanted Books",
        "item_type": "book",
        "build_fn": _build_most_wanted,
    },
    {
        "key": "trending_reads",
        "display_name": "Trending Right Now",
        "item_type": "book",
        "build_fn": _build_trending_reads,
    },
    {
        "key": "most_viewed",
        "display_name": "Most Popular",
        "item_type": "book",
        "build_fn": _build_most_viewed,
    },
    {
        "key": "highest_rated",
        "display_name": "Highest Rated",
        "item_type": "book",
        "build_fn": _build_highest_rated,
    },
    {
        "key": "community_top_rated",
        "display_name": "Community Favorites",
        "item_type": "book",
        "build_fn": _build_community_top_rated,
    },
    {
        "key": "most_rated",
        "display_name": "Most Reviewed",
        "item_type": "book",
        "build_fn": _build_most_rated,
    },
    {
        "key": "recently_added",
        "display_name": "Recently Added",
        "item_type": "book",
        "build_fn": _build_recently_added,
    },
    {
        "key": "classics",
        "display_name": "Classic Books",
        "item_type": "book",
        "build_fn": _build_classics,
    },
    {
        "key": "user_favorites",
        "display_name": "User Favorites",
        "item_type": "book",
        "build_fn": _build_user_favorites,
    },
    {
        "key": "recently_finished",
        "display_name": "Recently Finished",
        "item_type": "book",
        "build_fn": _build_recently_finished,
    },
    {
        "key": "currently_reading",
        "display_name": "Currently Being Read",
        "item_type": "book",
        "build_fn": _build_currently_reading,
    },
    {
        "key": "best_writing",
        "display_name": "Best Writing",
        "item_type": "book",
        "build_fn": _build_best_writing,
    },
    {
        "key": "most_emotional",
        "display_name": "Most Emotional",
        "item_type": "book",
        "build_fn": _build_most_emotional,
    },
    {
        "key": "funniest",
        "display_name": "Funniest Books",
        "item_type": "book",
        "build_fn": _build_funniest,
    },
    {
        "key": "most_thought_provoking",
        "display_name": "Most Thought-Provoking",
        "item_type": "book",
        "build_fn": _build_most_thought_provoking,
    },
    {
        "key": "most_rereadable",
        "display_name": "Most Rereadable",
        "item_type": "book",
        "build_fn": _build_most_rereadable,
    },
    {
        "key": "top_authors",
        "display_name": "Most Read Authors",
        "item_type": "author",
        "build_fn": _build_top_authors,
    },
    {
        "key": "popular_authors",
        "display_name": "Popular Authors",
        "item_type": "author",
        "build_fn": _build_popular_authors,
    },
]

CATEGORY_KEYS: typing.Set[str] = {c["key"] for c in CATEGORIES}
CATEGORY_ITEM_TYPES: typing.Dict[str, str] = {c["key"]: c["item_type"] for c in CATEGORIES}


def get_category_item_type(category: str) -> typing.Optional[str]:
    return CATEGORY_ITEM_TYPES.get(category)


async def _collect_series_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.Set[int],
) -> typing.Set[int]:
    if not book_ids:
        return set()
    result = await session.execute(
        sqlalchemy.text(
            "SELECT DISTINCT series_id FROM books.books "
            "WHERE book_id = ANY(:ids) AND series_id IS NOT NULL"
        ),
        {"ids": list(book_ids)},
    )
    return {row.series_id for row in result}


async def _precache_contextual(
    session_maker: typing.Any,
    ids: typing.Set[int],
    builder_fn: typing.Callable,
    key_prefix: str,
    ttl: int,
    limit: int,
) -> None:
    if not ids:
        return

    sem = asyncio.Semaphore(5)

    async def _one(eid: int) -> bool:
        async with sem:
            try:
                sections = await builder_fn(session_maker, eid, limit)
                if sections:
                    await app.cache.set_cached(f"{key_prefix}:{eid}", sections, ttl)
                    return True
            except Exception:
                logger.exception(f"[rec] precache {key_prefix}:{eid} failed")
            return False

    results = await asyncio.gather(*(_one(i) for i in ids))
    logger.info(
        f"[rec] Precached {sum(results)}/{len(ids)} contextual recs for {key_prefix}"
    )


def recommendation_list_cache_key(category: str, item_type: str, language: str) -> str:
    if item_type == "author":
        return f"rec:{category}"
    return f"rec:{category}:{language}"


async def refresh_all(session_maker: sqlalchemy.orm.sessionmaker) -> None:
    settings = app.config.settings
    logger.info("[rec] Starting recommendation list refresh")

    languages = app.services.book_of_week_builder.available_languages()
    book_ids: typing.Set[int] = set()
    author_ids: typing.Set[int] = set()

    for category in CATEGORIES:
        key = category["key"]
        item_type = category["item_type"]
        build_languages = languages if item_type == "book" else [languages[0]]

        for language in build_languages:
            try:
                async with session_maker() as session:
                    if item_type == "book":
                        items = await category["build_fn"](
                            session, settings.list_default_size * 2, language
                        )
                    else:
                        items = await category["build_fn"](
                            session, settings.list_default_size * 2
                        )
                items_key = "book_items" if item_type == "book" else "author_items"
                payload = {
                    "category": key,
                    "display_name": category["display_name"],
                    "item_type": item_type,
                    items_key: items,
                    "total": len(items),
                }
                cache_key = recommendation_list_cache_key(key, item_type, language)
                await app.cache.set_cached(
                    cache_key, payload, settings.cache_recommendation_ttl
                )
                logger.info(f"[rec] Cached {len(items)} items for '{cache_key}'")
                if item_type == "book":
                    for item in items:
                        bid = item.get("book_id")
                        if bid:
                            book_ids.add(bid)
                elif item_type == "author":
                    for item in items:
                        aid = item.get("author_id")
                        if aid:
                            author_ids.add(aid)
            except Exception:
                logger.exception(f"[rec] Failed to build category '{key}' ({language})")

    logger.info("[rec] Recommendation list refresh complete")

    ttl = settings.cache_recommendation_ttl
    precache_limit = 10

    async with session_maker() as session:
        series_ids = await _collect_series_ids(session, book_ids)

    await _precache_contextual(
        session_maker,
        book_ids,
        app.services.book_recommender.build_book_recommendations,
        "rec:book",
        ttl,
        precache_limit,
    )
    await _precache_contextual(
        session_maker,
        author_ids,
        app.services.author_recommender.build_author_recommendations,
        "rec:author",
        ttl,
        precache_limit,
    )
    await _precache_contextual(
        session_maker,
        series_ids,
        app.services.series_recommender.build_series_recommendations,
        "rec:series",
        ttl,
        precache_limit,
    )
