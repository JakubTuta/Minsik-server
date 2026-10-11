import typing

import app.services._language_boost
import sqlalchemy
import sqlalchemy.ext.asyncio

# Same popularity and rating signals the category pages have always sorted by, reduced with
# MAX per work like books.work_rank: Open Library counts sit on whichever edition OL
# recorded them against.
_RATING_SCORE_SQL = (
    "CASE"
    " WHEN COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0) = 0 THEN 0"
    " ELSE ("
    "   COALESCE(b.avg_rating, 0) * COALESCE(b.rating_count, 0)"
    "   + COALESCE(b.ol_avg_rating, 0) * COALESCE(b.ol_rating_count, 0)"
    " ) / (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0))"
    " END"
)

_DELETE_SQL = sqlalchemy.text("DELETE FROM books.category_works WHERE category_slug = :slug")
_INSERT_SQL = sqlalchemy.text(
    f"""
    INSERT INTO books.category_works (category_slug, work_id, popularity, rating_score)
    SELECT :slug, b.work_id,
           MAX({app.services._language_boost.work_popularity_sql()}),
           MAX({_RATING_SCORE_SQL})
    FROM books.books b
    JOIN books.book_genres bg ON bg.book_id = b.book_id AND bg.genre_id = ANY(:genre_ids)
    {app.services._language_boost.work_shelf_counts_join()}
    WHERE b.primary_cover_url IS NOT NULL AND b.work_id IS NOT NULL
    GROUP BY b.work_id
    """
)
_COUNT_SQL = sqlalchemy.text("SELECT COUNT(*) FROM books.category_works WHERE category_slug = :slug")

_SORT_COLUMNS = {"popularity": "cw.popularity", "rating": "cw.rating_score"}


async def rebuild(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, genre_ids: typing.List[int]
) -> int:
    """Replace one category's rows in a single transaction, so readers see the old set or the new one."""
    await session.execute(_DELETE_SQL, {"slug": slug})
    result = await session.execute(_INSERT_SQL, {"slug": slug, "genre_ids": genre_ids})
    await session.commit()
    return result.rowcount or 0


async def count(session: sqlalchemy.ext.asyncio.AsyncSession, slug: str) -> int:
    return (await session.execute(_COUNT_SQL, {"slug": slug})).scalar_one()


def page_query(sort_by: str, order: str) -> sqlalchemy.TextClause:
    """One page of works in rank order, each rendered as the reader's language edition.

    Only the works on the page go through the edition lookup. `pos` carries the rank order
    through the join, which does not preserve it.
    """
    column = _SORT_COLUMNS.get(sort_by, _SORT_COLUMNS["popularity"])
    direction = "DESC" if order.lower() == "desc" else "ASC"

    return sqlalchemy.text(
        f"""
        WITH page AS (
            SELECT cw.work_id,
                   ROW_NUMBER() OVER (ORDER BY {column} {direction}, cw.work_id {direction}) AS pos
            FROM books.category_works cw
            WHERE cw.category_slug = :slug
            ORDER BY {column} {direction}, cw.work_id {direction}
            LIMIT :limit OFFSET :offset
        )
        SELECT
            b.book_id, b.title, b.slug, b.work_id, b.description,
            b.original_publication_year, b.primary_cover_url, b.language,
            b.rating_count, b.avg_rating, b.ol_rating_count, b.ol_avg_rating,
            b.ol_want_to_read_count, b.ol_currently_reading_count, b.ol_already_read_count,
            COALESCE(wsc.want_to_read_count, 0) AS app_want_to_read_count,
            COALESCE(wsc.reading_count, 0) AS app_reading_count,
            COALESCE(wsc.read_count, 0) AS app_read_count,
            (
                SELECT COALESCE(json_agg(json_build_object(
                    'author_id', a2.author_id,
                    'name', a2.name,
                    'slug', a2.slug,
                    'photo_url', a2.photo_url
                )), '[]'::json)
                FROM books.book_authors ba2
                JOIN books.authors a2 ON ba2.author_id = a2.author_id
                WHERE ba2.book_id = b.book_id
            ) AS authors
        FROM page
        JOIN LATERAL (
            SELECT e.* FROM books.books e
            WHERE e.work_id = page.work_id AND e.primary_cover_url IS NOT NULL
            ORDER BY (e.language = :language) DESC, (e.language = 'en') DESC, e.book_id ASC
            LIMIT 1
        ) b ON TRUE
        {app.services._language_boost.work_shelf_counts_join()}
        ORDER BY page.pos
        """
    )
