import datetime
import logging
import typing

import app.cache
import app.config
import app.models.author
import app.models.book
import app.models.book_author
import app.models.book_genre
import app.models.genre
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


async def get_author_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"author_slug:{slug}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_author_view(cached["author_id"])
        return cached

    stmt = select(app.models.author.Author).filter(
        app.models.author.Author.slug == slug
    )

    result = await session.execute(stmt)
    author = result.scalar_one_or_none()

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
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"author_books:{author_slug}:limit:{limit}:offset:{offset}:sort:{sort_by}:order:{order}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["books"], cached["total"]

    author_stmt = select(app.models.author.Author).filter(
        app.models.author.Author.slug == author_slug
    )
    author_result = await session.execute(author_stmt)
    author = author_result.scalar_one_or_none()

    if not author:
        return [], 0

    sort_column = _get_sort_column(sort_by)
    order_func = sqlalchemy.desc if order == "desc" else sqlalchemy.asc

    stmt = (
        select(app.models.book.Book)
        .join(app.models.book_author.BookAuthor)
        .options(selectinload(app.models.book.Book.genres))
        .filter(app.models.book_author.BookAuthor.author_id == author.author_id)
        .order_by(order_func(sort_column).nullslast())
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
        app.config.settings.cache_author_books_ttl,
    )

    return books_data, total


async def _track_author_view(author_id: int) -> None:
    try:
        await app.cache.increment_view_count("author", author_id)
    except Exception as e:
        logger.error(f"Failed to track author view: {str(e)}")


def _get_sort_column(sort_by: str):
    sort_mapping = {
        "publication_year": app.models.book.Book.original_publication_year,
        "avg_rating": app.models.book.Book.avg_rating,
        "view_count": app.models.book.Book.view_count,
    }
    return sort_mapping.get(sort_by, app.models.book.Book.view_count)


async def _get_author_book_categories(
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int
) -> typing.List[str]:
    stmt = (
        select(app.models.genre.Genre.name)
        .select_from(app.models.book_genre.BookGenre)
        .join(
            app.models.book_author.BookAuthor,
            app.models.book_genre.BookGenre.book_id
            == app.models.book_author.BookAuthor.book_id,
        )
        .join(
            app.models.genre.Genre,
            app.models.book_genre.BookGenre.genre_id == app.models.genre.Genre.genre_id,
        )
        .filter(app.models.book_author.BookAuthor.author_id == author_id)
        .distinct()
    )

    result = await session.execute(stmt)
    categories = [row[0] for row in result.fetchall()]
    return categories


async def _get_author_books_aggregates(
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int
) -> typing.Dict[str, typing.Any]:
    stmt = (
        select(
            func.count().label("books_count"),
            func.sum(
                app.models.book.Book.avg_rating * app.models.book.Book.rating_count
            ).label("weighted_rating_sum"),
            func.sum(app.models.book.Book.rating_count).label("total_ratings"),
            func.sum(app.models.book.Book.view_count).label("total_views"),
        )
        .select_from(app.models.book.Book)
        .join(app.models.book_author.BookAuthor)
        .filter(app.models.book_author.BookAuthor.author_id == author_id)
    )

    result = await session.execute(stmt)
    row = result.first()

    total_ratings = int(row.total_ratings) if row.total_ratings else 0
    weighted_rating_sum = (
        float(row.weighted_rating_sum) if row.weighted_rating_sum else 0.0
    )
    avg_rating = (
        round(weighted_rating_sum / total_ratings, 2) if total_ratings > 0 else 0.0
    )

    return {
        "books_count": int(row.books_count) if row.books_count else 0,
        "avg_rating": avg_rating,
        "total_ratings": total_ratings,
        "total_views": int(row.total_views) if row.total_views else 0,
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
        "books_total_views": books_aggregates["total_views"],
        "open_library_id": author.open_library_id or None,
        "created_at": author.created_at.isoformat() if author.created_at else "",
        "updated_at": author.updated_at.isoformat() if author.updated_at else "",
        "wikidata_id": author.wikidata_id or None,
        "wikipedia_url": author.wikipedia_url or None,
        "remote_ids": author.remote_ids or {},
        "alternate_names": author.alternate_names or [],
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
            {"genre_id": genre.genre_id, "name": genre.name, "slug": genre.slug}
            for genre in book.genres
        ],
    }


async def flush_view_counts_to_db(session: sqlalchemy.ext.asyncio.AsyncSession) -> None:
    try:
        pending_counts = await app.cache.get_pending_view_counts("author")

        if not pending_counts:
            return

        for author_id, data in pending_counts.items():
            stmt = sqlalchemy.text(
                """
                UPDATE books.authors
                SET
                    view_count = view_count + :increment,
                    last_viewed_at = to_timestamp(:last_viewed)
                WHERE author_id = :author_id
            """
            )

            await session.execute(
                stmt,
                {
                    "author_id": author_id,
                    "increment": data["count"],
                    "last_viewed": data["last_viewed"],
                },
            )

        await session.commit()

        await app.cache.clear_view_counts("author", list(pending_counts.keys()))

        logger.info(f"Flushed {len(pending_counts)} author view counts to database")
    except Exception as e:
        logger.error(f"Failed to flush author view counts: {str(e)}")
        await session.rollback()
