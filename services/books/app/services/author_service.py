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
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def get_author_by_slug(
    session: sqlalchemy.ext.asyncio.AsyncSession, slug: str, language: str = "en"
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    cache_key = f"author_slug:{slug}:{language}"
    cached = await app.cache.get_cached(cache_key)
    if cached:
        await _track_author_view(cached["author_id"])
        return cached

    stmt = select(app.models.author.Author).filter(
        app.models.author.Author.slug == slug
    )

    result = await session.execute(stmt)
    author = result.scalars().first()

    if not author:
        return None

    book_categories = await _get_author_book_categories(
        session, author.author_id, language
    )
    books_aggregates = await _get_author_books_aggregates(
        session, author.author_id, language
    )

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

    author_stmt = select(app.models.author.Author).filter(
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
            b.series_id,
            b.series_position,
            COALESCE(bs.want_to_read_count, 0) AS app_want_to_read_count,
            COALESCE(bs.reading_count, 0) AS app_reading_count,
            COALESCE(bs.read_count, 0) AS app_read_count,
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
        JOIN books.book_authors ba ON b.book_id = ba.book_id
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
        WHERE ba.author_id = :author_id AND b.language = :language
        GROUP BY
            b.book_id, b.title, b.slug, b.description, b.original_publication_year,
            b.primary_cover_url, b.rating_count, b.avg_rating, b.view_count,
            b.ol_rating_count, b.ol_avg_rating, b.ol_want_to_read_count,
            b.ol_currently_reading_count, b.ol_already_read_count,
            b.series_id, b.series_position,
            bs.want_to_read_count, bs.reading_count, bs.read_count
        ORDER BY {sort_col} {order_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
        """
    )

    count_query = sqlalchemy.text(
        """
        SELECT COUNT(DISTINCT b.book_id)
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
        WHERE ba.author_id = :author_id AND b.language = :language
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
        count_query, {"author_id": author.author_id, "language": language}
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
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int, language: str
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
            app.models.book.Book,
            app.models.book_genre.BookGenre.book_id == app.models.book.Book.book_id,
        )
        .join(
            app.models.genre.Genre,
            app.models.book_genre.BookGenre.genre_id == app.models.genre.Genre.genre_id,
        )
        .filter(
            app.models.book_author.BookAuthor.author_id == author_id,
            app.models.book.Book.language == language,
        )
        .distinct()
    )

    result = await session.execute(stmt)
    categories = [row[0] for row in result.fetchall()]
    return categories


async def _get_author_books_aggregates(
    session: sqlalchemy.ext.asyncio.AsyncSession, author_id: int, language: str
) -> typing.Dict[str, typing.Any]:
    stmt = sqlalchemy.text(
        """
        SELECT
            COUNT(*) AS books_count,
            COALESCE(SUM(b.avg_rating::numeric * b.rating_count), 0) AS weighted_rating_sum,
            COALESCE(SUM(b.rating_count), 0) AS total_ratings,
            COALESCE(SUM(b.ol_rating_count), 0) AS ol_total_ratings,
            COALESCE(SUM(b.ol_avg_rating::numeric * b.ol_rating_count), 0) AS ol_weighted_rating_sum,
            COALESCE(SUM(b.ol_want_to_read_count), 0) AS ol_want_to_read_count,
            COALESCE(SUM(b.ol_currently_reading_count), 0) AS ol_currently_reading_count,
            COALESCE(SUM(b.ol_already_read_count), 0) AS ol_already_read_count,
            COALESCE(SUM(bs_counts.want_to_read_count), 0) AS app_want_to_read_count,
            COALESCE(SUM(bs_counts.reading_count), 0) AS app_reading_count,
            COALESCE(SUM(bs_counts.read_count), 0) AS app_read_count
        FROM books.books b
        JOIN books.book_authors ba ON b.book_id = ba.book_id
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
        WHERE ba.author_id = :author_id AND b.language = :language
        """
    )

    result = await session.execute(stmt, {"author_id": author_id, "language": language})
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
        "genres": genres_list,
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
