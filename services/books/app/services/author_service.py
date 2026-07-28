import logging
import typing

import app.cache
import app.config
import app.models.author
import app.models.book
import app.models.book_author
import app.models.book_genre
import app.models.genre
import app.services._language_boost
import app.services._row_helpers
import app.services._user_stats
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


async def get_author_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str = "en"
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"author_slug:{slug}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_author_view(cached["author_id"])
        return cached

    stmt = sqlalchemy.select(app.models.author.Author).filter(
        app.models.author.Author.slug == slug
    )

    result = await session.execute(stmt)
    author = result.scalars().first()

    if not author:
        return None

    book_categories = await _get_author_book_categories(session, author.author_id)
    books_aggregates = await _get_author_books_aggregates(session, author.author_id)

    author_data = _author_to_dict(author, book_categories, books_aggregates)

    await app.cache.set_cached(
        cache_key, author_data, app.config.settings.cache_author_detail_ttl
    )

    await _track_author_view(author.author_id)

    return author_data


async def get_author_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_slug: str,
    limit: int,
    offset: int,
    sort_by: str = "view_count",
    order: str = "desc",
    language: str = "en",
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"author_books:{author_slug}:limit:{limit}:offset:{offset}:sort:{sort_by}:order:{order}:lang:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["books"], cached["total"]

    author_stmt = sqlalchemy.select(app.models.author.Author).filter(
        app.models.author.Author.slug == author_slug
    )
    author_result = await session.execute(author_stmt)
    author = author_result.scalars().first()

    if not author:
        return [], 0

    sort_options = {
        "publication_year": "b.original_publication_year",
        "combined_rating": "combined_rating",
        "readers_count": "total_readers",
    }
    sort_col = sort_options.get(sort_by, "combined_rating")
    order_dir = "DESC" if order == "desc" else "ASC"
    # An author's catalog is their works, not their translations: list every
    # work once, rendered in the reader's language when that edition exists.
    preferred_edition = app.services._language_boost.preferred_edition_sql(
        require_cover=False
    )

    books_query = sqlalchemy.text(
        f"""
        SELECT
            b.book_id,
            b.title,
            b.slug,
            b.description,
            b.original_publication_year,
            b.primary_cover_url,
            b.rating_count,
            b.avg_rating,
            b.ol_rating_count,
            b.ol_avg_rating,
            b.ol_want_to_read_count,
            b.ol_currently_reading_count,
            b.ol_already_read_count,
            COALESCE(wsc.want_to_read_count, 0) AS app_want_to_read_count,
            COALESCE(wsc.reading_count, 0) AS app_reading_count,
            COALESCE(wsc.read_count, 0) AS app_read_count,
            CASE
                WHEN (b.rating_count + b.ol_rating_count) > 0
                THEN (
                    COALESCE(b.avg_rating::numeric, 0) * b.rating_count
                    + COALESCE(b.ol_avg_rating::numeric, 0) * b.ol_rating_count
                ) / (b.rating_count + b.ol_rating_count)
                ELSE 0
            END AS combined_rating,
            (
                b.ol_want_to_read_count + b.ol_currently_reading_count + b.ol_already_read_count
                + COALESCE(wsc.want_to_read_count, 0)
                + COALESCE(wsc.reading_count, 0)
                + COALESCE(wsc.read_count, 0)
            ) AS total_readers,
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
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        {app.services._language_boost.work_shelf_counts_join()}
        WHERE ba.author_id = :author_id AND {preferred_edition}
        ORDER BY {sort_col} {order_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
        """
    )

    count_query = sqlalchemy.text(
        """
        SELECT COUNT(DISTINCT b.work_id)
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        WHERE ba.author_id = :author_id
        """
    )

    books_result = await session.execute(
        books_query,
        {
            "author_id": author.author_id,
            "language": language,
            "limit": limit,
            "offset": offset,
        },
    )
    books_rows = books_result.fetchall()

    count_result = await session.execute(
        count_query, {"author_id": author.author_id}
    )
    total = count_result.scalar() or 0

    books_data = [_book_row_to_dict(row) for row in books_rows]

    await app.cache.set_cached(
        cache_key,
        {"books": books_data, "total": total},
        app.config.settings.cache_author_books_ttl,
    )

    return books_data, total


async def _track_author_view(author_id: int) -> None:
    try:
        await app.cache.increment_view_count("author", author_id)
    except Exception as e:
        logger.error(f"Failed to track author view: {str(e)}")


async def _get_author_book_categories(
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int
) -> typing.List[str]:
    # Language-agnostic: an author's genre categorization reflects their whole
    # catalog. Counts distinct works (not book rows) so a translated book
    # doesn't count once per edition toward the >= 3 threshold.
    stmt = (
        sqlalchemy.select(app.models.genre.Genre.name)
        .select_from(app.models.book_genre.BookGenre)
        .join(
            app.models.book_author.BookAuthor,
            app.models.book_genre.BookGenre.book_id
            == app.models.book_author.BookAuthor.book_id,
        )
        .join(
            app.models.book.Book,
            app.models.book_genre.BookGenre.book_id == app.models.book.Book.book_id,
        )
        .join(
            app.models.genre.Genre,
            app.models.book_genre.BookGenre.genre_id == app.models.genre.Genre.genre_id,
        )
        .filter(app.models.book_author.BookAuthor.author_id == author_id)
        .group_by(app.models.genre.Genre.name)
        .having(sqlalchemy.func.count(sqlalchemy.func.distinct(app.models.book.Book.work_id)) >= 3)
        .order_by(sqlalchemy.func.count(sqlalchemy.func.distinct(app.models.book.Book.work_id)).desc())
    )

    result = await session.execute(stmt)
    categories = [row[0] for row in result.fetchall()]
    return categories


async def _get_author_books_aggregates(
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int
) -> typing.Dict[str, typing.Any]:
    # Language-agnostic and deduped by work: an author's stats reflect their
    # whole catalog, one row per work (picking the most-rated edition), so a
    # translated book's already-pooled rating_count isn't summed once per
    # edition. Reader/status counts are pooled across all editions per work.
    stmt = sqlalchemy.text(
        """
        WITH author_works AS (
            SELECT DISTINCT ON (b.work_id)
                b.book_id, b.work_id, b.rating_count, b.avg_rating,
                b.ol_rating_count, b.ol_avg_rating,
                b.ol_want_to_read_count, b.ol_currently_reading_count, b.ol_already_read_count
            FROM books.books b
            JOIN books.book_authors ba ON b.book_id = ba.book_id
            WHERE ba.author_id = :author_id
            ORDER BY b.work_id, (COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)) DESC
        ),
        work_bookshelf_counts AS (
            SELECT
                wsc.work_id,
                wsc.want_to_read_count,
                wsc.reading_count,
                wsc.read_count
            FROM books.work_shelf_counts wsc
            WHERE wsc.work_id IN (SELECT work_id FROM author_works)
        )
        SELECT
            COUNT(*) AS books_count,
            COALESCE(SUM(aw.avg_rating::numeric * aw.rating_count), 0) AS weighted_rating_sum,
            COALESCE(SUM(aw.rating_count), 0) AS total_ratings,
            COALESCE(SUM(aw.ol_rating_count), 0) AS ol_total_ratings,
            COALESCE(SUM(aw.ol_avg_rating::numeric * aw.ol_rating_count), 0) AS ol_weighted_rating_sum,
            COALESCE(SUM(aw.ol_want_to_read_count), 0) AS ol_want_to_read_count,
            COALESCE(SUM(aw.ol_currently_reading_count), 0) AS ol_currently_reading_count,
            COALESCE(SUM(aw.ol_already_read_count), 0) AS ol_already_read_count,
            COALESCE(SUM(wbc.want_to_read_count), 0) AS app_want_to_read_count,
            COALESCE(SUM(wbc.reading_count), 0) AS app_reading_count,
            COALESCE(SUM(wbc.read_count), 0) AS app_read_count
        FROM author_works aw
        LEFT JOIN work_bookshelf_counts wbc ON wbc.work_id = aw.work_id
        """
    )

    result = await session.execute(stmt, {"author_id": author_id})
    row = result.first()

    total_ratings = int(row.total_ratings) if row.total_ratings else 0
    weighted_rating_sum = (
        float(row.weighted_rating_sum) if row.weighted_rating_sum else 0.0
    )
    avg_rating = (
        round(weighted_rating_sum / total_ratings, 2) if total_ratings > 0 else 0.0
    )

    ol_total_ratings = int(row.ol_total_ratings) if row.ol_total_ratings else 0
    ol_weighted_rating_sum = (
        float(row.ol_weighted_rating_sum) if row.ol_weighted_rating_sum else 0.0
    )
    ol_avg_rating = (
        round(ol_weighted_rating_sum / ol_total_ratings, 2)
        if ol_total_ratings > 0
        else 0.0
    )

    return {
        "books_count": int(row.books_count) if row.books_count else 0,
        "avg_rating": avg_rating,
        "total_ratings": total_ratings,
        "ol_avg_rating": ol_avg_rating,
        "ol_total_ratings": ol_total_ratings,
        "ol_want_to_read_count": (
            int(row.ol_want_to_read_count) if row.ol_want_to_read_count else 0
        ),
        "ol_currently_reading_count": (
            int(row.ol_currently_reading_count) if row.ol_currently_reading_count else 0
        ),
        "ol_already_read_count": (
            int(row.ol_already_read_count) if row.ol_already_read_count else 0
        ),
        "app_want_to_read_count": (
            int(row.app_want_to_read_count) if row.app_want_to_read_count else 0
        ),
        "app_reading_count": int(row.app_reading_count) if row.app_reading_count else 0,
        "app_read_count": int(row.app_read_count) if row.app_read_count else 0,
    }


def _author_to_dict(
    author: app.models.author.Author,
    book_categories: typing.List[str],
    books_aggregates: typing.Dict[str, typing.Any],
) -> typing.Dict[str, typing.Any]:
    return {
        "author_id": author.author_id,
        "name": author.name,
        "slug": author.slug,
        "bio": author.bio or None,
        "birth_date": author.birth_date.isoformat() if author.birth_date else None,
        "death_date": author.death_date.isoformat() if author.death_date else None,
        "birth_place": author.birth_place or None,
        "nationality": author.nationality or None,
        "photo_url": author.photo_url or None,
        "view_count": author.view_count or 0,
        "last_viewed_at": (
            author.last_viewed_at.isoformat() if author.last_viewed_at else None
        ),
        "books_count": books_aggregates["books_count"],
        "book_categories": book_categories,
        "books_avg_rating": str(books_aggregates["avg_rating"]),
        "books_total_ratings": books_aggregates["total_ratings"],
        "books_ol_avg_rating": str(books_aggregates["ol_avg_rating"]),
        "books_ol_total_ratings": books_aggregates["ol_total_ratings"],
        "app_want_to_read_count": books_aggregates["app_want_to_read_count"],
        "app_reading_count": books_aggregates["app_reading_count"],
        "app_read_count": books_aggregates["app_read_count"],
        "ol_want_to_read_count": books_aggregates["ol_want_to_read_count"],
        "ol_currently_reading_count": books_aggregates["ol_currently_reading_count"],
        "ol_already_read_count": books_aggregates["ol_already_read_count"],
        "open_library_id": author.open_library_id or None,
        "created_at": author.created_at.isoformat() if author.created_at else "",
        "updated_at": author.updated_at.isoformat() if author.updated_at else "",
        "wikidata_id": author.wikidata_id or None,
        "wikipedia_url": author.wikipedia_url or None,
        "remote_ids": author.remote_ids or {},
        "alternate_names": author.alternate_names or [],
    }


def _book_row_to_dict(row: typing.Any) -> typing.Dict[str, typing.Any]:
    authors_list = app.services._row_helpers.json_agg_list(row.authors)
    return {
        "book_id": row.book_id,
        "title": row.title,
        "slug": row.slug,
        "description": row.description or "",
        "original_publication_year": int(row.original_publication_year or 0),
        "primary_cover_url": row.primary_cover_url or "",
        "rating_count": row.rating_count or 0,
        "avg_rating": str(row.avg_rating) if row.avg_rating else "0.00",
        "ol_rating_count": row.ol_rating_count or 0,
        "ol_avg_rating": str(row.ol_avg_rating) if row.ol_avg_rating else "0.00",
        "ol_want_to_read_count": row.ol_want_to_read_count or 0,
        "ol_currently_reading_count": row.ol_currently_reading_count or 0,
        "ol_already_read_count": row.ol_already_read_count or 0,
        "app_want_to_read_count": row.app_want_to_read_count or 0,
        "app_reading_count": row.app_reading_count or 0,
        "app_read_count": row.app_read_count or 0,
        "authors": authors_list,
    }


async def update_author(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
    updates: typing.Dict[str, typing.Any],
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    stmt = sqlalchemy.select(app.models.author.Author).filter(
        app.models.author.Author.author_id == author_id
    )

    result = await session.execute(stmt)
    author = result.scalars().first()

    if not author:
        return None

    old_slug = author.slug

    for field, value in updates.items():
        setattr(author, field, value)

    await session.commit()
    await session.refresh(author)

    await app.cache.delete_localized("author_slug", old_slug)
    await app.cache.delete_localized("author_books", old_slug)
    if author.slug != old_slug:
        await app.cache.delete_localized("author_slug", author.slug)
        await app.cache.delete_localized("author_books", author.slug)

    book_categories = await _get_author_book_categories(session, author.author_id)
    books_aggregates = await _get_author_books_aggregates(session, author.author_id)

    return _author_to_dict(author, book_categories, books_aggregates)


async def flush_view_counts_to_db(session: sqlalchemy.ext.asyncio.AsyncSession) -> None:
    try:
        count = await app.cache.flush_view_counts(session, "author", "books.authors", "author_id")
        if count:
            logger.info(f"Flushed {count} author view counts to database")
    except Exception as e:
        logger.error(f"Failed to flush author view counts: {str(e)}")
        await session.rollback()


async def delete_author(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_id: int,
) -> typing.Dict[str, typing.Any]:
    stmt = sqlalchemy.select(app.models.author.Author).filter(
        app.models.author.Author.author_id == author_id
    )
    result = await session.execute(stmt)
    author = result.scalars().first()

    if not author:
        raise ValueError("not_found")

    slug = author.slug
    name = author.name

    sole_books_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT b.book_id, b.slug, b.language, b.series_id
            FROM books.books b
            JOIN books.book_authors ba ON b.book_id = ba.book_id
            WHERE ba.author_id = :author_id
            GROUP BY b.book_id, b.slug, b.language, b.series_id
            HAVING COUNT(ba.author_id) = 1
            """
        ),
        {"author_id": author_id},
    )
    sole_books = sole_books_result.fetchall()
    sole_book_ids = [row.book_id for row in sole_books]

    if sole_book_ids:
        ids_placeholder = ",".join(str(bid) for bid in sole_book_ids)

        affected_users_result = await session.execute(
            sqlalchemy.text(
                f"""
                SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id IN ({ids_placeholder})
                UNION
                SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id IN ({ids_placeholder})
                UNION
                SELECT DISTINCT user_id FROM user_data.comments WHERE book_id IN ({ids_placeholder})
                """
            )
        )
        affected_user_ids = [row.user_id for row in affected_users_result.fetchall()]

        await session.execute(
            sqlalchemy.text(f"DELETE FROM user_data.comments WHERE book_id IN ({ids_placeholder})")
        )
        await session.execute(
            sqlalchemy.text(f"DELETE FROM user_data.ratings WHERE book_id IN ({ids_placeholder})")
        )
        await session.execute(
            sqlalchemy.text(f"DELETE FROM user_data.bookshelves WHERE book_id IN ({ids_placeholder})")
        )

        await app.services._user_stats.recalculate(session, affected_user_ids)

        await session.execute(
            sqlalchemy.text(f"DELETE FROM books.book_genres WHERE book_id IN ({ids_placeholder})")
        )
        await session.execute(
            sqlalchemy.text(f"DELETE FROM books.book_authors WHERE book_id IN ({ids_placeholder})")
        )
        await session.execute(
            sqlalchemy.text(f"DELETE FROM books.books WHERE book_id IN ({ids_placeholder})")
        )

    await session.delete(author)
    await session.flush()

    sole_book_series_ids = list({row.series_id for row in sole_books if row.series_id is not None})
    if sole_book_series_ids:
        series_placeholder = ",".join(str(sid) for sid in sole_book_series_ids)
        await session.execute(
            sqlalchemy.text(
                f"""
                DELETE FROM books.series
                WHERE series_id IN ({series_placeholder})
                  AND NOT EXISTS (
                      SELECT 1 FROM books.books b WHERE b.series_id = books.series.series_id
                  )
                """
            )
        )

    await session.commit()

    await app.cache.delete_localized("author_slug", slug)
    await app.cache.delete_localized("author_books", slug)
    for book in sole_books:
        await app.cache.delete_localized("book_slug", book.slug)
        await app.cache.delete_localized("book_lang_variants", book.slug)

    return {"author_id": author_id, "name": name}
