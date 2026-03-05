import logging
import typing

import app.config
import app.models
import app.workers.scheduler
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy.engine import CursorResult

logger = logging.getLogger(__name__)

_DUMP_RUNNING_KEY = "dump_import_running"


def _create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=app.config.settings.redis_host,
        port=app.config.settings.redis_port,
        db=app.config.settings.redis_db,
        password=app.config.settings.redis_password or None,
        decode_responses=True,
    )


async def cleanup_low_quality_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    min_quality_score: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    quality_score_sql = """
        (CASE WHEN b.description IS NOT NULL AND b.description != '' THEN 1 ELSE 0 END) +
        (CASE WHEN b.primary_cover_url IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id) THEN 1 ELSE 0 END) +
        (CASE WHEN EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id) THEN 1 ELSE 0 END) +
        (CASE WHEN b.original_publication_year IS NOT NULL THEN 1 ELSE 0 END) +
        (CASE WHEN b.isbn IS NOT NULL AND b.isbn != '[]'::jsonb THEN 1 ELSE 0 END) +
        (CASE WHEN b.number_of_pages IS NOT NULL AND b.number_of_pages > 0 THEN 1 ELSE 0 END) +
        (CASE WHEN b.publisher IS NOT NULL AND b.publisher != '' THEN 1 ELSE 0 END)
    """

    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT COUNT(*) FROM books.books b
            WHERE ({quality_score_sql}) < :min_score
              AND b.rating_count = 0
              AND b.view_count = 0
              AND COALESCE(b.ol_rating_count, 0) = 0
              AND COALESCE(b.ol_already_read_count, 0) = 0
              AND b.created_at < NOW() - INTERVAL '1 day'
              AND NOT EXISTS (
                  SELECT 1 FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id
              )
        """
        ),
        {"min_score": min_quality_score},
    )
    total_eligible = result.scalar_one()

    if total_eligible == 0:
        return {"deleted": 0, "eligible": 0}

    logger.info(
        f"[cleanup] Found {total_eligible} low-quality books eligible for deletion"
    )

    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping book cleanup: dump import started")
            break
        result = await session.execute(
            sqlalchemy.text(
                f"""
                DELETE FROM books.books
                WHERE book_id IN (
                    SELECT b.book_id FROM books.books b
                    WHERE ({quality_score_sql}) < :min_score
                      AND b.rating_count = 0
                      AND b.view_count = 0
                      AND COALESCE(b.ol_rating_count, 0) = 0
                      AND COALESCE(b.ol_already_read_count, 0) = 0
                      AND b.created_at < NOW() - INTERVAL '1 day'
                      AND NOT EXISTS (
                          SELECT 1 FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id
                      )
                    LIMIT :batch_size
                )
            """
            ),
            {"min_score": min_quality_score, "batch_size": batch_size},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

        if deleted == 0:
            break

        total_deleted += deleted
        logger.info(
            f"[cleanup] Deleted {total_deleted}/{total_eligible} low-quality books"
        )
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted, "eligible": total_eligible}


async def cleanup_orphan_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    min_books: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    result = await session.execute(
        sqlalchemy.text(
            f"""
            SELECT COUNT(*) FROM books.authors a
            LEFT JOIN (
                SELECT author_id, COUNT(*) AS book_count
                FROM books.book_authors
                GROUP BY author_id
            ) ba ON ba.author_id = a.author_id
            WHERE COALESCE(ba.book_count, 0) < :min_books
            AND a.view_count = 0
            AND a.created_at < NOW() - INTERVAL '1 day'
        """
        ),
        {"min_books": min_books},
    )
    total_eligible = result.scalar_one()

    if total_eligible == 0:
        return {"deleted": 0, "eligible": 0}

    logger.info(f"[cleanup] Found {total_eligible} authors eligible for deletion")

    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping author cleanup: dump import started")
            break
        result = await session.execute(
            sqlalchemy.text(
                f"""
                DELETE FROM books.authors
                WHERE author_id IN (
                    SELECT a.author_id FROM books.authors a
                    LEFT JOIN (
                        SELECT author_id, COUNT(*) AS book_count
                        FROM books.book_authors
                        GROUP BY author_id
                    ) ba ON ba.author_id = a.author_id
                    WHERE COALESCE(ba.book_count, 0) < :min_books
                    AND a.view_count = 0
                    AND a.created_at < NOW() - INTERVAL '1 day'
                    LIMIT :batch_size
                )
            """
            ),
            {"min_books": min_books, "batch_size": batch_size},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

        if deleted == 0:
            break

        total_deleted += deleted
        logger.info(
            f"[cleanup] Deleted {total_deleted}/{total_eligible} low-relevance authors"
        )
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted, "eligible": total_eligible}


async def cleanup_orphan_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping series cleanup: dump import started")
            break
        result = await session.execute(
            sqlalchemy.text(
                """
                DELETE FROM books.series
                WHERE series_id IN (
                    SELECT s.series_id FROM books.series s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM books.books b WHERE b.series_id = s.series_id
                    )
                    AND s.view_count = 0
                    AND s.created_at < NOW() - INTERVAL '1 day'
                    LIMIT :batch_size
                )
            """
            ),
            {"batch_size": batch_size},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def cleanup_orphan_genres(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping genre cleanup: dump import started")
            break
        result = await session.execute(
            sqlalchemy.text(
                """
                DELETE FROM books.genres
                WHERE genre_id IN (
                    SELECT g.genre_id FROM books.genres g
                    WHERE NOT EXISTS (
                        SELECT 1 FROM books.book_genres bg WHERE bg.genre_id = g.genre_id
                    )
                    LIMIT :batch_size
                )
            """
            ),
            {"batch_size": batch_size},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def run_cleanup_cycle(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, typing.Any]:
    batch_size = app.config.settings.cleanup_batch_size
    min_quality = app.config.settings.cleanup_book_min_quality_score
    min_books = app.config.settings.cleanup_author_min_books

    book_stats = await cleanup_low_quality_books(
        session, min_quality, batch_size, stop_check
    )
    if stop_check():
        return {
            "books": book_stats,
            "authors": {"deleted": 0, "eligible": 0},
            "series_deleted": 0,
            "genres_deleted": 0,
        }
    author_stats = await cleanup_orphan_authors(
        session, min_books, batch_size, stop_check
    )
    if stop_check():
        return {
            "books": book_stats,
            "authors": author_stats,
            "series_deleted": 0,
            "genres_deleted": 0,
        }
    series_deleted = await cleanup_orphan_series(session, batch_size, stop_check)
    if stop_check():
        return {
            "books": book_stats,
            "authors": author_stats,
            "series_deleted": series_deleted,
            "genres_deleted": 0,
        }
    genres_deleted = await cleanup_orphan_genres(session, batch_size, stop_check)

    return {
        "books": book_stats,
        "authors": author_stats,
        "series_deleted": series_deleted,
        "genres_deleted": genres_deleted,
    }


async def run_cleanup_job() -> None:
    if not app.config.settings.cleanup_enabled:
        return

    redis_client: typing.Optional[redis.Redis] = None
    try:
        redis_client = _create_redis_client()
    except Exception as e:
        logger.warning(f"[cleanup] Failed to connect to Redis: {e}")

    try:
        if redis_client is not None and redis_client.get(_DUMP_RUNNING_KEY):
            logger.info("Skipping cleanup cycle: dump import in progress")
            return

        def stop_check() -> bool:
            if redis_client is None:
                return False
            try:
                return bool(redis_client.get(_DUMP_RUNNING_KEY))
            except Exception:
                return False

        async with app.models.AsyncSessionLocal() as session:
            stats = await run_cleanup_cycle(session, stop_check)

        logger.info(
            f"[cleanup] Cycle complete: "
            f"{stats['books']['deleted']} books, "
            f"{stats['authors']['deleted']} authors, "
            f"{stats['series_deleted']} series, "
            f"{stats['genres_deleted']} genres deleted"
        )

    except Exception as e:
        logger.error(f"[cleanup] Cleanup cycle failed: {str(e)}")
    finally:
        if redis_client is not None:
            redis_client.close()
