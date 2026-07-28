import logging
import typing

import app.cache
import app.config
import app.models.author
import app.models.book
import app.models.genre
import app.services._user_stats
import sqlalchemy
import sqlalchemy.ext.asyncio
import sqlalchemy.orm

logger = logging.getLogger(__name__)


def _book_query_options() -> typing.List[typing.Any]:
    return [
        sqlalchemy.orm.selectinload(app.models.book.Book.authors),
        sqlalchemy.orm.selectinload(app.models.book.Book.genres),
        sqlalchemy.orm.selectinload(app.models.book.Book.series),
    ]


async def _fallback_edition(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str
) -> typing.Optional[app.models.book.Book]:
    # No edition in the requested language for this slug's work — fall back to
    # the best available edition (preferred language -> English -> most
    # ratings) instead of a dead-end 404. _book_to_dict()'s "language" field
    # then reflects the edition actually served.
    #
    # slug alone isn't unique (only (language, slug) is) — two unrelated works
    # in different languages can coincidentally slugify to the same string.
    # Order by english-first, then book_id, so the pick is deterministic
    # instead of whatever row the planner happens to return first.
    work_id_subquery = (
        sqlalchemy.select(app.models.book.Book.work_id)
        .filter(app.models.book.Book.slug == slug)
        .order_by(
            (app.models.book.Book.language == "en").desc(),
            app.models.book.Book.book_id.asc(),
        )
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        sqlalchemy.select(app.models.book.Book)
        .options(*_book_query_options())
        .filter(app.models.book.Book.work_id == work_id_subquery)
    )
    result = await session.execute(stmt)
    editions = result.scalars().all()
    if not editions:
        return None

    for edition in editions:
        if edition.language == language:
            return edition
    for edition in editions:
        if edition.language == "en":
            return edition
    return max(
        editions,
        key=lambda b: (b.rating_count or 0) + (b.ol_rating_count or 0),
    )


async def get_book_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str = "en"
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"book_slug:{slug}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_book_view(cached["book_id"])
        return cached

    stmt = (
        sqlalchemy.select(app.models.book.Book)
        .options(*_book_query_options())
        .filter(
            app.models.book.Book.slug == slug,
            app.models.book.Book.language == language,
        )
    )

    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        book = await _fallback_edition(session, slug, language)

    if not book:
        return None

    book_data = _book_to_dict(book)

    await _attach_work_stats(session, book_data, book.work_id)

    await app.cache.set_cached(
        cache_key, book_data, app.config.settings.cache_book_detail_ttl
    )

    await _track_book_view(book.book_id)

    return book_data


async def _attach_work_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_data: typing.Dict[str, typing.Any],
    work_id: str,
) -> None:
    """Overlay community stats pooled across every language edition of the work.

    A reader who shelved two translations counts once, so the numbers are the
    same whichever edition the page is rendered in.
    """
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                (
                    SELECT COALESCE(SUM(view_count), 0)
                    FROM books.books WHERE work_id = :work_id
                ) AS view_count,
                COUNT(DISTINCT user_id) FILTER (WHERE status = 'want_to_read')
                    AS app_want_to_read_count,
                COUNT(DISTINCT user_id) FILTER (WHERE status = 'reading')
                    AS app_reading_count,
                COUNT(DISTINCT user_id) FILTER (WHERE status = 'read')
                    AS app_read_count
            FROM user_data.bookshelves
            WHERE book_id IN (SELECT book_id FROM books.books WHERE work_id = :work_id)
            """
        ),
        {"work_id": work_id},
    )
    row = result.first()
    book_data["view_count"] = int(row.view_count or 0) if row else 0
    book_data["app_want_to_read_count"] = int(row.app_want_to_read_count or 0) if row else 0
    book_data["app_reading_count"] = int(row.app_reading_count or 0) if row else 0
    book_data["app_read_count"] = int(row.app_read_count or 0) if row else 0


async def get_language_variants(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    slug: str,
    exclude_language: str = "en",
) -> typing.List[typing.Dict[str, typing.Any]]:
    cache_key = f"book_lang_variants:{slug}:{exclude_language}"
    cached = await app.cache.get_cached(cache_key)
    if cached is not None:
        return cached

    stmt = sqlalchemy.text(
        "SELECT book_id, slug, language, title, primary_cover_url "
        "FROM books.books "
        "WHERE work_id = ("
        "  SELECT work_id FROM books.books WHERE slug = :slug "
        "  ORDER BY (language = :exclude_language) DESC, (language = 'en') DESC, book_id ASC "
        "  LIMIT 1"
        ") "
        "AND language != :exclude_language"
    )
    result = await session.execute(stmt, {"slug": slug, "exclude_language": exclude_language})
    rows = result.fetchall()

    variants = [
        {
            "book_id": row.book_id,
            "slug": row.slug,
            "language": row.language,
            "title": row.title,
            "primary_cover_url": row.primary_cover_url or "",
        }
        for row in rows
    ]

    await app.cache.set_cached(cache_key, variants, app.config.settings.cache_book_detail_ttl)
    return variants


async def _track_book_view(book_id: int) -> None:
    try:
        await app.cache.increment_view_count("book", book_id)
    except Exception as e:
        logger.error(f"Failed to track book view: {str(e)}")


def _book_to_dict(book: app.models.book.Book) -> typing.Dict[str, typing.Any]:
    series_dict = None
    if book.series:
        series_dict = {
            "series_id": book.series.series_id,
            "name": book.series.name,
            "slug": book.series.slug,
            "total_books": book.series.total_books,
        }

    return {
        "book_id": book.book_id,
        "work_id": book.work_id,
        "title": book.title,
        "slug": book.slug,
        "description": book.description or "",
        "first_sentence": book.first_sentence or "",
        "language": book.language,
        "original_publication_year": book.original_publication_year or 0,
        "formats": book.formats or [],
        "primary_cover_url": book.primary_cover_url or "",
        "rating_count": book.rating_count or 0,
        "avg_rating": str(book.avg_rating) if book.avg_rating else "0.00",
        "sub_rating_stats": book.sub_rating_stats or {},
        "view_count": book.view_count or 0,
        "last_viewed_at": (
            book.last_viewed_at.isoformat() if book.last_viewed_at else ""
        ),
        "authors": [
            {
                "author_id": author.author_id,
                "name": author.name,
                "slug": author.slug,
                "photo_url": author.photo_url or "",
            }
            for author in book.authors
        ],
        "genres": [
            {"genre_id": genre.genre_id, "name": genre.name, "slug": genre.slug}
            for genre in book.genres
        ],
        "open_library_id": book.open_library_id or "",
        "google_books_id": book.google_books_id or "",
        "created_at": book.created_at.isoformat() if book.created_at else "",
        "updated_at": book.updated_at.isoformat() if book.updated_at else "",
        "series": series_dict,
        "series_position": str(book.series_position) if book.series_position else "",
        "isbn": book.isbn or [],
        "publisher": book.publisher or "",
        "number_of_pages": book.number_of_pages or 0,
        "external_ids": book.external_ids or {},
        "ol_rating_count": book.ol_rating_count or 0,
        "ol_avg_rating": str(book.ol_avg_rating) if book.ol_avg_rating else "0.00",
        "ol_want_to_read_count": book.ol_want_to_read_count or 0,
        "ol_currently_reading_count": book.ol_currently_reading_count or 0,
        "ol_already_read_count": book.ol_already_read_count or 0,
        "rating_distribution": book.rating_distribution or {},
    }


async def update_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    updates: typing.Dict[str, typing.Any],
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    stmt = (
        sqlalchemy.select(app.models.book.Book)
        .options(
            sqlalchemy.orm.selectinload(app.models.book.Book.authors),
            sqlalchemy.orm.selectinload(app.models.book.Book.genres),
            sqlalchemy.orm.selectinload(app.models.book.Book.series),
        )
        .filter(app.models.book.Book.book_id == book_id)
    )

    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        return None

    old_slug = book.slug

    for field, value in updates.items():
        setattr(book, field, value)

    if "series_id" in updates:
        new_series_id = updates["series_id"]
        if new_series_id is None:
            if "series_position" not in updates:
                book.series_position = None
            book.series_slug = None
            book.series_name = None
        else:
            series_row_result = await session.execute(
                sqlalchemy.text("SELECT slug, name FROM books.series WHERE series_id = :id"),
                {"id": new_series_id},
            )
            series_row = series_row_result.first()
            if series_row:
                book.series_slug = series_row.slug
                book.series_name = series_row.name

    await session.commit()

    fresh_stmt = (
        sqlalchemy.select(app.models.book.Book)
        .options(
            sqlalchemy.orm.selectinload(app.models.book.Book.authors),
            sqlalchemy.orm.selectinload(app.models.book.Book.genres),
            sqlalchemy.orm.selectinload(app.models.book.Book.series),
        )
        .filter(app.models.book.Book.book_id == book_id)
    )
    fresh_result = await session.execute(fresh_stmt)
    book = fresh_result.scalars().first()

    if not book:
        return None

    await app.cache.delete_localized("book_slug", old_slug)
    await app.cache.delete_localized("book_lang_variants", old_slug)
    if book.slug != old_slug:
        await app.cache.delete_localized("book_slug", book.slug)
        await app.cache.delete_localized("book_lang_variants", book.slug)

    book_data = _book_to_dict(book)

    await _attach_work_stats(session, book_data, book.work_id)

    return book_data


async def remove_book_author(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
    author_id: int,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    stmt = (
        sqlalchemy.select(app.models.book.Book)
        .options(
            sqlalchemy.orm.selectinload(app.models.book.Book.authors),
            sqlalchemy.orm.selectinload(app.models.book.Book.genres),
            sqlalchemy.orm.selectinload(app.models.book.Book.series),
        )
        .filter(app.models.book.Book.book_id == book_id)
    )
    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        return None

    author_to_remove = next((a for a in book.authors if a.author_id == author_id), None)
    if not author_to_remove:
        raise ValueError("author_not_on_book")

    author_slug = author_to_remove.slug
    book.authors.remove(author_to_remove)
    await session.commit()

    fresh_result = await session.execute(stmt)
    book = fresh_result.scalars().first()

    if not book:
        return None

    await app.cache.delete_localized("book_slug", book.slug)
    await app.cache.delete_localized("book_lang_variants", book.slug)
    await app.cache.delete_localized("author_slug", author_slug)
    await app.cache.delete_localized("author_books", author_slug)

    book_data = _book_to_dict(book)

    await _attach_work_stats(session, book_data, book.work_id)

    return book_data


async def flush_view_counts_to_db(session: sqlalchemy.ext.asyncio.AsyncSession) -> None:
    try:
        count = await app.cache.flush_view_counts(session, "book", "books.books", "book_id")
        if count:
            logger.info(f"Flushed {count} book view counts to database")
    except Exception as e:
        logger.error(f"Failed to flush book view counts: {str(e)}")
        await session.rollback()


async def delete_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
) -> typing.Dict[str, typing.Any]:
    stmt = sqlalchemy.select(app.models.book.Book).filter(app.models.book.Book.book_id == book_id)
    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        raise ValueError("not_found")

    slug = book.slug
    title = book.title

    affected_users_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id = :book_id
            UNION
            SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id = :book_id
            UNION
            SELECT DISTINCT user_id FROM user_data.comments WHERE book_id = :book_id
            """
        ),
        {"book_id": book_id},
    )
    affected_user_ids = [row.user_id for row in affected_users_result.fetchall()]

    comments_result = await session.execute(
        sqlalchemy.text("DELETE FROM user_data.comments WHERE book_id = :book_id"),
        {"book_id": book_id},
    )
    comments_deleted = comments_result.rowcount

    ratings_result = await session.execute(
        sqlalchemy.text("DELETE FROM user_data.ratings WHERE book_id = :book_id"),
        {"book_id": book_id},
    )
    ratings_deleted = ratings_result.rowcount

    bookshelves_result = await session.execute(
        sqlalchemy.text("DELETE FROM user_data.bookshelves WHERE book_id = :book_id"),
        {"book_id": book_id},
    )
    bookshelves_deleted = bookshelves_result.rowcount

    await session.delete(book)
    await session.flush()

    await app.services._user_stats.recalculate(session, affected_user_ids)

    await session.commit()
    await app.cache.delete_localized("book_slug", slug)
    await app.cache.delete_localized("book_lang_variants", slug)

    return {
        "book_id": book_id,
        "title": title,
        "bookshelves_deleted": bookshelves_deleted,
        "ratings_deleted": ratings_deleted,
        "comments_deleted": comments_deleted,
        "users_recalculated": len(affected_user_ids),
    }
