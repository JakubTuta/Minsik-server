import datetime
import logging
import typing

import app.cache
import app.config
import app.models.book
import app.models.series
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


async def get_series_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"series_slug:{slug}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_series_view(cached["series_id"])
        return cached

    stmt = select(app.models.series.Series).filter(
        app.models.series.Series.slug == slug
    )

    result = await session.execute(stmt)
    series = result.scalar_one_or_none()

    if not series:
        return None

    stats_query = text(
        """
        SELECT
            COUNT(*) as total_books,
            COALESCE(SUM(rating_count), 0) as rating_count,
            CASE
                WHEN SUM(rating_count) > 0
                THEN ROUND(SUM(avg_rating::numeric * rating_count) / SUM(rating_count), 2)
                ELSE NULL
            END as avg_rating,
            COALESCE(SUM(ol_rating_count), 0) as ol_rating_count,
            CASE
                WHEN SUM(ol_rating_count) > 0
                THEN ROUND(SUM(ol_avg_rating::numeric * ol_rating_count) / SUM(ol_rating_count), 2)
                ELSE NULL
            END as ol_avg_rating,
            COALESCE(SUM(view_count), 0) as total_views
        FROM books.books
        WHERE series_id = :series_id
    """
    )
    stats_result = await session.execute(stats_query, {"series_id": series.series_id})
    stats = stats_result.first()

    series_data = _series_to_dict(series, stats)

    await app.cache.set_cached(
        cache_key, series_data, app.config.settings.cache_author_detail_ttl
    )

    await _track_series_view(series.series_id)

    return series_data


async def get_series_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    series_slug: str,
    limit: int,
    offset: int,
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"series_books:{series_slug}:limit:{limit}:offset:{offset}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["books"], cached["total"]

    series_stmt = select(app.models.series.Series).filter(
        app.models.series.Series.slug == series_slug
    )
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
            app.models.book.Book.created_at.asc(),
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
            "avg_rating": str(book.avg_rating) if book.avg_rating else "0.00",
            "view_count": book.view_count,
            "series_position": (
                str(book.series_position) if book.series_position else None
            ),
            "genres": [
                {"genre_id": genre.genre_id, "name": genre.name, "slug": genre.slug}
                for genre in book.genres
            ],
        }
        books_list.append(book_dict)

    result_data = {"books": books_list, "total": total_count}

    await app.cache.set_cached(
        cache_key, result_data, app.config.settings.cache_author_books_ttl
    )

    return books_list, total_count


def _series_to_dict(
    series: app.models.series.Series, stats: typing.Any
) -> typing.Dict[str, typing.Any]:
    return {
        "series_id": series.series_id,
        "name": series.name,
        "slug": series.slug,
        "description": series.description,
        "total_books": stats.total_books or 0,
        "view_count": series.view_count,
        "last_viewed_at": (
            series.last_viewed_at.isoformat() if series.last_viewed_at else None
        ),
        "created_at": series.created_at.isoformat() if series.created_at else None,
        "updated_at": series.updated_at.isoformat() if series.updated_at else None,
        "avg_rating": str(stats.avg_rating) if stats.avg_rating else None,
        "rating_count": stats.rating_count or 0,
        "ol_avg_rating": str(stats.ol_avg_rating) if stats.ol_avg_rating else None,
        "ol_rating_count": stats.ol_rating_count or 0,
        "total_views": stats.total_views or 0,
    }


async def _track_series_view(series_id: int) -> None:
    try:
        await app.cache.increment_view_count("series", series_id)
    except Exception as e:
        logger.error(f"Error tracking series view: {str(e)}")
