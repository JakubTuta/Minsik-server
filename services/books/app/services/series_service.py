import typing
import logging
import datetime
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import app.config
import app.models.series
import app.models.book
import app.cache

logger = logging.getLogger(__name__)


async def get_series_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    slug: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"series_slug:{slug}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_series_view(cached["series_id"])
        return cached

    stmt = select(app.models.series.Series).filter(app.models.series.Series.slug == slug)

    result = await session.execute(stmt)
    series = result.scalar_one_or_none()

    if not series:
        return None

    books_count_stmt = (
        select(func.count())
        .select_from(app.models.book.Book)
        .filter(app.models.book.Book.series_id == series.series_id)
    )
    books_count_result = await session.execute(books_count_stmt)
    books_count = books_count_result.scalar() or 0

    series_data = _series_to_dict(series, books_count)

    await app.cache.set_cached(
        cache_key,
        series_data,
        app.config.settings.cache_author_detail_ttl
    )

    await _track_series_view(series.series_id)

    return series_data


async def get_series_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_slug: str,
    limit: int,
    offset: int
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"series_books:{series_slug}:limit:{limit}:offset:{offset}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["books"], cached["total"]

    series_stmt = select(app.models.series.Series).filter(app.models.series.Series.slug == series_slug)
    series_result = await session.execute(series_stmt)
    series = series_result.scalar_one_or_none()

    if not series:
        return [], 0

    stmt = (
        select(app.models.book.Book)
        .options(selectinload(app.models.book.Book.genres))
        .filter(app.models.book.Book.series_id == series.series_id)
        .order_by(
            app.models.book.Book.series_position.asc().nullslast(),
            app.models.book.Book.created_at.asc()
        )
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(stmt)
    books = result.scalars().all()

    count_stmt = (
        select(func.count())
        .select_from(app.models.book.Book)
        .filter(app.models.book.Book.series_id == series.series_id)
    )
    count_result = await session.execute(count_stmt)
    total_count = count_result.scalar() or 0

    books_list = []
    for book in books:
        book_dict = {
            "book_id": book.book_id,
            "title": book.title,
            "slug": book.slug,
            "description": book.description,
            "original_publication_year": book.original_publication_year,
            "primary_cover_url": book.primary_cover_url,
            "rating_count": book.rating_count,
            "avg_rating": str(book.avg_rating) if book.avg_rating else None,
            "view_count": book.view_count,
            "series_position": str(book.series_position) if book.series_position else None,
            "genres": [
                {
                    "genre_id": genre.genre_id,
                    "name": genre.name,
                    "slug": genre.slug
                }
                for genre in book.genres
            ]
        }
        books_list.append(book_dict)

    result_data = {
        "books": books_list,
        "total": total_count
    }

    await app.cache.set_cached(
        cache_key,
        result_data,
        app.config.settings.cache_author_books_ttl
    )

    return books_list, total_count


def _series_to_dict(series: app.models.series.Series, books_count: int) -> typing.Dict[str, typing.Any]:
    return {
        "series_id": series.series_id,
        "name": series.name,
        "slug": series.slug,
        "description": series.description,
        "total_books": books_count,
        "view_count": series.view_count,
        "last_viewed_at": series.last_viewed_at.isoformat() if series.last_viewed_at else None,
        "created_at": series.created_at.isoformat() if series.created_at else None,
        "updated_at": series.updated_at.isoformat() if series.updated_at else None,
    }


async def _track_series_view(series_id: int) -> None:
    try:
        await app.cache.increment_view_count("series", series_id)
    except Exception as e:
        logger.error(f"Error tracking series view: {str(e)}")
