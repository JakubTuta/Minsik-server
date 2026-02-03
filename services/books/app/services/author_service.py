import typing
import logging
import datetime
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import app.config
import app.models.author
import app.models.book
import app.models.book_author
import app.cache

logger = logging.getLogger(__name__)


async def get_author_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    slug: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"author_slug:{slug}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_author_view(cached["author_id"])
        return cached

    stmt = select(app.models.author.Author).filter(app.models.author.Author.slug == slug)

    result = await session.execute(stmt)
    author = result.scalar_one_or_none()

    if not author:
        return None

    books_count_stmt = (
        select(func.count())
        .select_from(app.models.book_author.BookAuthor)
        .filter(app.models.book_author.BookAuthor.author_id == author.author_id)
    )
    books_count_result = await session.execute(books_count_stmt)
    books_count = books_count_result.scalar() or 0

    author_data = _author_to_dict(author, books_count)

    await app.cache.set_cached(
        cache_key,
        author_data,
        app.config.settings.cache_author_detail_ttl
    )

    await _track_author_view(author.author_id)

    return author_data


async def get_author_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    author_slug: str,
    limit: int,
    offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"author_books:{author_slug}:limit:{limit}:offset:{offset}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["books"], cached["total"]

    author_stmt = select(app.models.author.Author).filter(app.models.author.Author.slug == author_slug)
    author_result = await session.execute(author_stmt)
    author = author_result.scalar_one_or_none()

    if not author:
        return [], 0

    stmt = (
        select(app.models.book.Book)
        .join(app.models.book_author.BookAuthor)
        .options(selectinload(app.models.book.Book.genres))
        .filter(app.models.book_author.BookAuthor.author_id == author.author_id)
        .order_by(
            app.models.book.Book.view_count.desc().nullslast(),
            app.models.book.Book.rating_count.desc().nullslast(),
            app.models.book.Book.created_at.desc()
        )
        .limit(limit)
        .offset(offset)
    )

    count_stmt = (
        select(func.count())
        .select_from(app.models.book_author.BookAuthor)
        .filter(app.models.book_author.BookAuthor.author_id == author.author_id)
    )

    result = await session.execute(stmt)
    books = result.scalars().all()

    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    books_data = [_book_summary_to_dict(book) for book in books]

    await app.cache.set_cached(
        cache_key,
        {"books": books_data, "total": total},
        app.config.settings.cache_author_books_ttl
    )

    return books_data, total


async def _track_author_view(author_id: int) -> None:
    try:
        await app.cache.increment_view_count("author", author_id)
    except Exception as e:
        logger.error(f"Failed to track author view: {str(e)}")


def _author_to_dict(author: app.models.author.Author, books_count: int) -> typing.Dict[str, typing.Any]:
    return {
        "author_id": author.author_id,
        "name": author.name,
        "slug": author.slug,
        "bio": author.bio or "",
        "birth_date": author.birth_date.isoformat() if author.birth_date else "",
        "death_date": author.death_date.isoformat() if author.death_date else "",
        "photo_url": author.photo_url or "",
        "view_count": author.view_count or 0,
        "last_viewed_at": author.last_viewed_at.isoformat() if author.last_viewed_at else "",
        "books_count": books_count,
        "open_library_id": author.open_library_id or "",
        "created_at": author.created_at.isoformat() if author.created_at else "",
        "updated_at": author.updated_at.isoformat() if author.updated_at else ""
    }


def _book_summary_to_dict(book: app.models.book.Book) -> typing.Dict[str, typing.Any]:
    return {
        "book_id": book.book_id,
        "title": book.title,
        "slug": book.slug,
        "description": book.description or "",
        "original_publication_year": book.original_publication_year or 0,
        "primary_cover_url": book.primary_cover_url or "",
        "rating_count": book.rating_count or 0,
        "avg_rating": str(book.avg_rating) if book.avg_rating else "0.00",
        "view_count": book.view_count or 0,
        "genres": [
            {
                "genre_id": genre.genre_id,
                "name": genre.name,
                "slug": genre.slug
            }
            for genre in book.genres
        ]
    }


async def flush_view_counts_to_db(session: sqlalchemy.ext.asyncio.AsyncSession) -> None:
    try:
        pending_counts = await app.cache.get_pending_view_counts("author")

        if not pending_counts:
            return

        for author_id, data in pending_counts.items():
            stmt = sqlalchemy.text("""
                UPDATE books.authors
                SET
                    view_count = view_count + :increment,
                    last_viewed_at = to_timestamp(:last_viewed)
                WHERE author_id = :author_id
            """)

            await session.execute(
                stmt,
                {
                    "author_id": author_id,
                    "increment": data["count"],
                    "last_viewed": data["last_viewed"]
                }
            )

        await session.commit()

        await app.cache.clear_view_counts("author", list(pending_counts.keys()))

        logger.info(f"Flushed {len(pending_counts)} author view counts to database")
    except Exception as e:
        logger.error(f"Failed to flush author view counts: {str(e)}")
        await session.rollback()
