import datetime
import logging
import typing

import app.cache
import app.config
import app.models.author
import app.models.book
import app.models.genre
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


async def get_book_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str = "en"
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"book_slug:{slug}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_book_view(cached["book_id"])
        return cached

    stmt = (
        select(app.models.book.Book)
        .options(
            selectinload(app.models.book.Book.authors),
            selectinload(app.models.book.Book.genres),
            selectinload(app.models.book.Book.series),
        )
        .filter(
            app.models.book.Book.slug == slug,
            app.models.book.Book.language == language,
        )
    )

    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        return None

    book_data = _book_to_dict(book)

    bookshelves_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'want_to_read') AS app_want_to_read_count,
                COUNT(*) FILTER (WHERE status = 'reading') AS app_reading_count,
                COUNT(*) FILTER (WHERE status = 'read') AS app_read_count
            FROM user_data.bookshelves
            WHERE book_id = :book_id AND status != 'abandoned'
            """
        ),
        {"book_id": book.book_id},
    )
    bookshelves_row = bookshelves_result.first()
    book_data["app_want_to_read_count"] = (
        int(bookshelves_row.app_want_to_read_count)
        if bookshelves_row and bookshelves_row.app_want_to_read_count
        else 0
    )
    book_data["app_reading_count"] = (
        int(bookshelves_row.app_reading_count)
        if bookshelves_row and bookshelves_row.app_reading_count
        else 0
    )
    book_data["app_read_count"] = (
        int(bookshelves_row.app_read_count)
        if bookshelves_row and bookshelves_row.app_read_count
        else 0
    )

    await app.cache.set_cached(
        cache_key, book_data, app.config.settings.cache_book_detail_ttl
    )

    await _track_book_view(book.book_id)

    return book_data


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
        select(app.models.book.Book)
        .options(
            selectinload(app.models.book.Book.authors),
            selectinload(app.models.book.Book.genres),
            selectinload(app.models.book.Book.series),
        )
        .filter(app.models.book.Book.book_id == book_id)
    )

    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        return None

    old_cache_key = f"book_slug:{book.slug}:{book.language}"

    for field, value in updates.items():
        setattr(book, field, value)

    await session.commit()
    await session.refresh(book)

    await app.cache.delete_cached(old_cache_key)
    if "slug" in updates or "language" in updates:
        new_cache_key = f"book_slug:{book.slug}:{book.language}"
        await app.cache.delete_cached(new_cache_key)

    book_data = _book_to_dict(book)

    bookshelves_result = await session.execute(
        sqlalchemy.text(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'want_to_read') AS app_want_to_read_count,
                COUNT(*) FILTER (WHERE status = 'reading') AS app_reading_count,
                COUNT(*) FILTER (WHERE status = 'read') AS app_read_count
            FROM user_data.bookshelves
            WHERE book_id = :book_id AND status != 'abandoned'
            """
        ),
        {"book_id": book.book_id},
    )
    bookshelves_row = bookshelves_result.first()
    book_data["app_want_to_read_count"] = (
        int(bookshelves_row.app_want_to_read_count)
        if bookshelves_row and bookshelves_row.app_want_to_read_count
        else 0
    )
    book_data["app_reading_count"] = (
        int(bookshelves_row.app_reading_count)
        if bookshelves_row and bookshelves_row.app_reading_count
        else 0
    )
    book_data["app_read_count"] = (
        int(bookshelves_row.app_read_count)
        if bookshelves_row and bookshelves_row.app_read_count
        else 0
    )

    return book_data


async def flush_view_counts_to_db(session: sqlalchemy.ext.asyncio.AsyncSession) -> None:
    try:
        pending_counts = await app.cache.get_pending_view_counts("book")

        if not pending_counts:
            return

        for book_id, data in pending_counts.items():
            stmt = sqlalchemy.text(
                """
                UPDATE books.books
                SET
                    view_count = view_count + :increment,
                    last_viewed_at = to_timestamp(:last_viewed)
                WHERE book_id = :book_id
            """
            )

            await session.execute(
                stmt,
                {
                    "book_id": book_id,
                    "increment": data["count"],
                    "last_viewed": data["last_viewed"],
                },
            )

        await session.commit()

        await app.cache.clear_view_counts("book", list(pending_counts.keys()))

        logger.info(f"Flushed {len(pending_counts)} book view counts to database")
    except Exception as e:
        logger.error(f"Failed to flush book view counts: {str(e)}")
        await session.rollback()


async def delete_book(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_id: int,
) -> typing.Dict[str, typing.Any]:
    stmt = select(app.models.book.Book).filter(app.models.book.Book.book_id == book_id)
    result = await session.execute(stmt)
    book = result.scalars().first()

    if not book:
        raise ValueError("not_found")

    slug = book.slug
    language = book.language
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

    for user_id in affected_user_ids:
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, want_to_read_count, reading_count, read_count, abandoned_count, favourites_count)
                SELECT
                    :user_id,
                    COUNT(CASE WHEN status = 'want_to_read' THEN 1 END),
                    COUNT(CASE WHEN status = 'reading'      THEN 1 END),
                    COUNT(CASE WHEN status = 'read'         THEN 1 END),
                    COUNT(CASE WHEN status = 'abandoned'    THEN 1 END),
                    COUNT(CASE WHEN is_favorite             THEN 1 END)
                FROM user_data.bookshelves
                WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET
                    want_to_read_count = EXCLUDED.want_to_read_count,
                    reading_count      = EXCLUDED.reading_count,
                    read_count         = EXCLUDED.read_count,
                    abandoned_count    = EXCLUDED.abandoned_count,
                    favourites_count   = EXCLUDED.favourites_count
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, ratings_count)
                SELECT :user_id, COUNT(*) FROM user_data.ratings WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET ratings_count = EXCLUDED.ratings_count
                """
            ),
            {"user_id": user_id},
        )
        await session.execute(
            sqlalchemy.text(
                """
                INSERT INTO user_data.user_stats (user_id, comments_count)
                SELECT :user_id, COUNT(*) FROM user_data.comments WHERE user_id = :user_id
                ON CONFLICT (user_id) DO UPDATE SET comments_count = EXCLUDED.comments_count
                """
            ),
            {"user_id": user_id},
        )

    await session.commit()
    await app.cache.delete_cached(f"book_slug:{slug}:{language}")

    return {
        "book_id": book_id,
        "title": title,
        "bookshelves_deleted": bookshelves_deleted,
        "ratings_deleted": ratings_deleted,
        "comments_deleted": comments_deleted,
        "users_recalculated": len(affected_user_ids),
    }
