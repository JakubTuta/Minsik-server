import logging
import typing

import app.cache
import app.config
import app.models.book
import app.models.series
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import select, text

logger = logging.getLogger(__name__)


async def get_series_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str = "en"
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"series_slug:{slug}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_series_view(cached["series_id"])
        return cached

    stmt = select(app.models.series.Series).filter(
        app.models.series.Series.slug == slug
    )

    result = await session.execute(stmt)
    series = result.scalars().first()

    if not series:
        return None

    stats_query = text(
        """
        SELECT
            COUNT(*) as total_books,
            COALESCE(SUM(b.rating_count), 0) as rating_count,
            CASE
                WHEN SUM(b.rating_count) > 0
                THEN ROUND(SUM(b.avg_rating::numeric * b.rating_count) / SUM(b.rating_count), 2)
                ELSE NULL
            END as avg_rating,
            COALESCE(SUM(b.ol_rating_count), 0) as ol_rating_count,
            CASE
                WHEN SUM(b.ol_rating_count) > 0
                THEN ROUND(SUM(b.ol_avg_rating::numeric * b.ol_rating_count) / SUM(b.ol_rating_count), 2)
                ELSE NULL
            END as ol_avg_rating,
            COALESCE(SUM(b.ol_want_to_read_count), 0) AS ol_want_to_read_count,
            COALESCE(SUM(b.ol_currently_reading_count), 0) AS ol_currently_reading_count,
            COALESCE(SUM(b.ol_already_read_count), 0) AS ol_already_read_count,
            COALESCE(SUM(bs_counts.want_to_read_count), 0) AS app_want_to_read_count,
            COALESCE(SUM(bs_counts.reading_count), 0) AS app_reading_count,
            COALESCE(SUM(bs_counts.read_count), 0) AS app_read_count
        FROM books.books b
        LEFT JOIN (
            SELECT
                book_id,
                COUNT(*) FILTER (WHERE status = 'want_to_read') AS want_to_read_count,
                COUNT(*) FILTER (WHERE status = 'reading') AS reading_count,
                COUNT(*) FILTER (WHERE status = 'read') AS read_count
            FROM user_data.bookshelves
            WHERE status != 'abandoned'
            GROUP BY book_id
        ) bs_counts ON b.book_id = bs_counts.book_id
        WHERE b.series_id = :series_id AND b.language = :language
    """
    )
    stats_result = await session.execute(
        stats_query, {"series_id": series.series_id, "language": language}
    )
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
    language: str = "en",
    sort_by: str = "series_position",
    order: str = "asc",
) -> typing.Tuple[typing.List[typing.Dict[str, typing.Any]], int]:
    cache_key = f"series_books:{series_slug}:limit:{limit}:offset:{offset}:lang:{language}:sort:{sort_by}:order:{order}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        return cached["books"], cached["total"]

    series_stmt = select(app.models.series.Series).filter(
        app.models.series.Series.slug == series_slug
    )
    series_result = await session.execute(series_stmt)
    series = series_result.scalars().first()

    if not series:
        return [], 0

    sort_options = {
        "series_position": "b.series_position",
        "publication_year": "b.original_publication_year",
        "combined_rating": "combined_rating",
        "readers_count": "total_readers",
    }
    sort_col = sort_options.get(sort_by, "b.series_position")
    order_dir = "DESC" if order == "desc" else "ASC"
    secondary_sort = (
        f", b.created_at {order_dir}" if sort_by == "series_position" else ""
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
            b.view_count,
            b.ol_rating_count,
            b.ol_avg_rating,
            b.ol_want_to_read_count,
            b.ol_currently_reading_count,
            b.ol_already_read_count,
            b.series_position,
            COALESCE(bs.want_to_read_count, 0) AS app_want_to_read_count,
            COALESCE(bs.reading_count, 0) AS app_reading_count,
            COALESCE(bs.read_count, 0) AS app_read_count,
            CASE
                WHEN (b.rating_count + b.ol_rating_count) > 0
                THEN (
                    COALESCE(b.avg_rating::numeric, 0) * b.rating_count
                    + (COALESCE(b.ol_avg_rating::numeric, 0) / 2.0) * b.ol_rating_count
                ) / (b.rating_count + b.ol_rating_count)
                ELSE 0
            END AS combined_rating,
            (
                b.ol_want_to_read_count + b.ol_currently_reading_count + b.ol_already_read_count
                + COALESCE(bs.want_to_read_count, 0)
                + COALESCE(bs.reading_count, 0)
                + COALESCE(bs.read_count, 0)
            ) AS total_readers,
            COALESCE(
                json_agg(
                    json_build_object('genre_id', g.genre_id, 'name', g.name, 'slug', g.slug)
                ) FILTER (WHERE g.genre_id IS NOT NULL),
                '[]'::json
            ) AS genres
        FROM books.books b
        LEFT JOIN books.book_genres bg ON b.book_id = bg.book_id
        LEFT JOIN books.genres g ON bg.genre_id = g.genre_id
        LEFT JOIN (
            SELECT
                book_id,
                COUNT(*) FILTER (WHERE status = 'want_to_read') AS want_to_read_count,
                COUNT(*) FILTER (WHERE status = 'reading') AS reading_count,
                COUNT(*) FILTER (WHERE status = 'read') AS read_count
            FROM user_data.bookshelves
            WHERE status != 'abandoned'
            GROUP BY book_id
        ) bs ON b.book_id = bs.book_id
        WHERE b.series_id = :series_id AND b.language = :language
        GROUP BY
            b.book_id, b.title, b.slug, b.description, b.original_publication_year,
            b.primary_cover_url, b.rating_count, b.avg_rating, b.view_count,
            b.ol_rating_count, b.ol_avg_rating, b.ol_want_to_read_count,
            b.ol_currently_reading_count, b.ol_already_read_count, b.series_position,
            bs.want_to_read_count, bs.reading_count, bs.read_count
        ORDER BY {sort_col} {order_dir} NULLS LAST{secondary_sort}
        LIMIT :limit OFFSET :offset
        """
    )

    count_query = sqlalchemy.text(
        """
        SELECT COUNT(*)
        FROM books.books b
        WHERE b.series_id = :series_id AND b.language = :language
        """
    )

    books_result = await session.execute(
        books_query,
        {
            "series_id": series.series_id,
            "language": language,
            "limit": limit,
            "offset": offset,
        },
    )
    books_rows = books_result.fetchall()

    count_result = await session.execute(
        count_query, {"series_id": series.series_id, "language": language}
    )
    total_count = count_result.scalar() or 0

    books_list = [_series_book_row_to_dict(row) for row in books_rows]

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
        "total_books": int(stats.total_books) if stats.total_books else 0,
        "view_count": series.view_count,
        "last_viewed_at": (
            series.last_viewed_at.isoformat() if series.last_viewed_at else None
        ),
        "created_at": series.created_at.isoformat() if series.created_at else None,
        "updated_at": series.updated_at.isoformat() if series.updated_at else None,
        "avg_rating": str(stats.avg_rating) if stats.avg_rating else None,
        "rating_count": int(stats.rating_count) if stats.rating_count else 0,
        "ol_avg_rating": str(stats.ol_avg_rating) if stats.ol_avg_rating else None,
        "ol_rating_count": int(stats.ol_rating_count) if stats.ol_rating_count else 0,
        "ol_want_to_read_count": (
            int(stats.ol_want_to_read_count) if stats.ol_want_to_read_count else 0
        ),
        "ol_currently_reading_count": (
            int(stats.ol_currently_reading_count)
            if stats.ol_currently_reading_count
            else 0
        ),
        "ol_already_read_count": (
            int(stats.ol_already_read_count) if stats.ol_already_read_count else 0
        ),
        "app_want_to_read_count": (
            int(stats.app_want_to_read_count) if stats.app_want_to_read_count else 0
        ),
        "app_reading_count": (
            int(stats.app_reading_count) if stats.app_reading_count else 0
        ),
        "app_read_count": int(stats.app_read_count) if stats.app_read_count else 0,
    }


def _series_book_row_to_dict(row: typing.Any) -> typing.Dict[str, typing.Any]:
    genres_raw = row.genres
    if isinstance(genres_raw, str):
        import json

        genres_list = json.loads(genres_raw)
    elif genres_raw is None:
        genres_list = []
    else:
        genres_list = genres_raw
    return {
        "book_id": row.book_id,
        "title": row.title,
        "slug": row.slug,
        "description": row.description or "",
        "original_publication_year": row.original_publication_year or 0,
        "primary_cover_url": row.primary_cover_url or "",
        "rating_count": row.rating_count or 0,
        "avg_rating": str(row.avg_rating) if row.avg_rating else "0.00",
        "view_count": row.view_count or 0,
        "ol_rating_count": row.ol_rating_count or 0,
        "ol_avg_rating": str(row.ol_avg_rating) if row.ol_avg_rating else "0.00",
        "ol_want_to_read_count": row.ol_want_to_read_count or 0,
        "ol_currently_reading_count": row.ol_currently_reading_count or 0,
        "ol_already_read_count": row.ol_already_read_count or 0,
        "app_want_to_read_count": row.app_want_to_read_count or 0,
        "app_reading_count": row.app_reading_count or 0,
        "app_read_count": row.app_read_count or 0,
        "series_position": str(row.series_position) if row.series_position else None,
        "genres": genres_list,
    }


async def _track_series_view(series_id: int) -> None:
    try:
        await app.cache.increment_view_count("series", series_id)
    except Exception as e:
        logger.error(f"Error tracking series view: {str(e)}")
