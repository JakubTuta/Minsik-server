import asyncio
import logging
import typing

import app.config
import app.models
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
              AND b.view_count = 0
              AND (b.rating_count + COALESCE(b.ol_rating_count, 0)) < 30
              AND (COALESCE(b.ol_already_read_count, 0) + (SELECT COUNT(*) FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id)) < 30
              AND b.created_at < NOW() - INTERVAL '1 day'
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
                      AND b.view_count = 0
                      AND (b.rating_count + COALESCE(b.ol_rating_count, 0)) < 30
                      AND (COALESCE(b.ol_already_read_count, 0) + (SELECT COUNT(*) FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id)) < 30
                      AND b.created_at < NOW() - INTERVAL '1 day'
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
            """
            SELECT COUNT(*) FROM books.authors a
            LEFT JOIN (
                SELECT author_id, COUNT(*) AS book_count
                FROM books.book_authors
                GROUP BY author_id
            ) ba ON ba.author_id = a.author_id
            WHERE COALESCE(ba.book_count, 0) <= :min_books
            AND a.view_count = 0
            AND a.created_at < NOW() - INTERVAL '1 day'
            AND (
                SELECT COALESCE(SUM(b.rating_count + COALESCE(b.ol_rating_count, 0)), 0)
                FROM books.books b
                JOIN books.book_authors ba2 ON ba2.book_id = b.book_id
                WHERE ba2.author_id = a.author_id
            ) < 30
            AND (
                SELECT COUNT(*)
                FROM user_data.bookshelves bs
                JOIN books.book_authors ba2 ON ba2.book_id = bs.book_id
                WHERE ba2.author_id = a.author_id
            ) < 30
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

        author_id_result = await session.execute(
            sqlalchemy.text(
                """
                SELECT a.author_id FROM books.authors a
                LEFT JOIN (
                    SELECT author_id, COUNT(*) AS book_count
                    FROM books.book_authors
                    GROUP BY author_id
                ) ba ON ba.author_id = a.author_id
                WHERE COALESCE(ba.book_count, 0) <= :min_books
                AND a.view_count = 0
                AND a.created_at < NOW() - INTERVAL '1 day'
                AND (
                    SELECT COALESCE(SUM(b.rating_count + COALESCE(b.ol_rating_count, 0)), 0)
                    FROM books.books b
                    JOIN books.book_authors ba2 ON ba2.book_id = b.book_id
                    WHERE ba2.author_id = a.author_id
                ) < 30
                AND (
                    SELECT COUNT(*)
                    FROM user_data.bookshelves bs
                    JOIN books.book_authors ba2 ON ba2.book_id = bs.book_id
                    WHERE ba2.author_id = a.author_id
                ) < 30
                LIMIT :batch_size
                """
            ),
            {"min_books": min_books, "batch_size": batch_size},
        )
        author_ids = [row[0] for row in author_id_result.fetchall()]

        if not author_ids:
            break

        book_id_result = await session.execute(
            sqlalchemy.text(
                """
                SELECT ba.book_id,
                       (SELECT COUNT(*) FROM books.book_authors ba2 WHERE ba2.book_id = ba.book_id) AS author_count
                FROM books.book_authors ba
                WHERE ba.author_id = ANY(:author_ids)
                """
            ),
            {"author_ids": author_ids},
        )
        sole_book_ids = []
        for row in book_id_result.fetchall():
            if row[1] == 1:
                sole_book_ids.append(row[0])

        if sole_book_ids:
            affected_users_result = await session.execute(
                sqlalchemy.text(
                    """
                    SELECT DISTINCT user_id FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)
                    UNION
                    SELECT DISTINCT user_id FROM user_data.ratings WHERE book_id = ANY(:book_ids)
                    UNION
                    SELECT DISTINCT user_id FROM user_data.comments WHERE book_id = ANY(:book_ids)
                    """
                ),
                {"book_ids": sole_book_ids},
            )
            affected_user_ids = [row[0] for row in affected_users_result.fetchall()]

            await session.execute(
                sqlalchemy.text(
                    "DELETE FROM user_data.comments WHERE book_id = ANY(:book_ids)"
                ),
                {"book_ids": sole_book_ids},
            )
            await session.execute(
                sqlalchemy.text(
                    "DELETE FROM user_data.ratings WHERE book_id = ANY(:book_ids)"
                ),
                {"book_ids": sole_book_ids},
            )
            await session.execute(
                sqlalchemy.text(
                    "DELETE FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)"
                ),
                {"book_ids": sole_book_ids},
            )
            await session.execute(
                sqlalchemy.text(
                    "DELETE FROM books.books WHERE book_id = ANY(:book_ids)"
                ),
                {"book_ids": sole_book_ids},
            )

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

        result = await session.execute(
            sqlalchemy.text(
                "DELETE FROM books.authors WHERE author_id = ANY(:author_ids)"
            ),
            {"author_ids": author_ids},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

        total_deleted += deleted
        logger.info(
            f"[cleanup] Deleted {total_deleted}/{total_eligible} low-relevance authors"
        )
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted, "eligible": total_eligible}


async def cleanup_underrepresented_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    max_books: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping series cleanup: dump import started")
            break

        series_id_result = await session.execute(
            sqlalchemy.text(
                """
                WITH series_stats AS (
                    SELECT
                        s.series_id,
                        COALESCE(COUNT(b.book_id), 0) AS book_count,
                        COALESCE(SUM(COALESCE(b.rating_count, 0) + COALESCE(b.ol_rating_count, 0)), 0) AS ratings_count,
                        COALESCE(SUM(
                            COALESCE(b.ol_want_to_read_count, 0)
                            + COALESCE(b.ol_currently_reading_count, 0)
                            + COALESCE(b.ol_already_read_count, 0)
                        ), 0) AS ol_readers,
                        (
                            TRIM(LOWER(COALESCE(s.name, ''))) = 'unknown'
                            OR TRIM(LOWER(COALESCE(s.slug, ''))) = 'unknown'
                            OR TRIM(LOWER(COALESCE(s.slug, ''))) LIKE 'unknown-%'
                        ) AS is_unknown
                    FROM books.series s
                    LEFT JOIN books.books b ON b.series_id = s.series_id
                    GROUP BY s.series_id, s.name, s.slug
                ),
                app_readers AS (
                    SELECT b.series_id, COUNT(*) AS app_readers
                    FROM user_data.bookshelves bs
                    JOIN books.books b ON b.book_id = bs.book_id
                    WHERE b.series_id IS NOT NULL
                    GROUP BY b.series_id
                )
                SELECT ss.series_id
                FROM series_stats ss
                LEFT JOIN app_readers ar ON ar.series_id = ss.series_id
                WHERE ss.book_count <= :max_books
                   OR (
                       ss.is_unknown
                       AND ss.ratings_count = 0
                       AND (ss.ol_readers + COALESCE(ar.app_readers, 0)) = 0
                   )
                LIMIT :batch_size
                """
            ),
            {"max_books": max_books, "batch_size": batch_size},
        )
        series_ids = [row[0] for row in series_id_result.fetchall()]

        if not series_ids:
            break

        await session.execute(
            sqlalchemy.text(
                """
                UPDATE books.books
                SET series_id = NULL, series_position = NULL
                WHERE series_id = ANY(:series_ids)
                """
            ),
            {"series_ids": series_ids},
        )

        result = await session.execute(
            sqlalchemy.text(
                "DELETE FROM books.series WHERE series_id = ANY(:series_ids)"
            ),
            {"series_ids": series_ids},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

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


async def cleanup_underrepresented_genres(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    min_book_count: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info(
                "[cleanup] Stopping underrepresented genre cleanup: dump import started"
            )
            break
        result = await session.execute(
            sqlalchemy.text(
                """
                DELETE FROM books.genres
                WHERE genre_id IN (
                    SELECT g.genre_id FROM books.genres g
                    LEFT JOIN (
                        SELECT genre_id, COUNT(*) AS book_count
                        FROM books.book_genres
                        GROUP BY genre_id
                    ) bg ON bg.genre_id = g.genre_id
                    WHERE COALESCE(bg.book_count, 0) <= :min_book_count
                    LIMIT :batch_size
                )
            """
            ),
            {"min_book_count": min_book_count, "batch_size": batch_size},
        )
        deleted = typing.cast(CursorResult, result).rowcount
        await session.commit()

        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def cleanup_invalid_genre_names(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info(
                "[cleanup] Stopping invalid genre name cleanup: dump import started"
            )
            break
        result = await session.execute(
            sqlalchemy.text(
                """
                DELETE FROM books.genres
                WHERE genre_id IN (
                    SELECT g.genre_id FROM books.genres g
                    WHERE g.name ~ '[^a-zA-Z0-9 -]'
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
            "underrepresented_genres_deleted": 0,
            "invalid_name_genres_deleted": 0,
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
            "underrepresented_genres_deleted": 0,
            "invalid_name_genres_deleted": 0,
        }
    series_deleted = await cleanup_underrepresented_series(
        session, 2, batch_size, stop_check
    )
    if stop_check():
        return {
            "books": book_stats,
            "authors": author_stats,
            "series_deleted": series_deleted,
            "genres_deleted": 0,
            "underrepresented_genres_deleted": 0,
            "invalid_name_genres_deleted": 0,
        }
    genres_deleted = await cleanup_orphan_genres(session, batch_size, stop_check)
    if stop_check():
        return {
            "books": book_stats,
            "authors": author_stats,
            "series_deleted": series_deleted,
            "genres_deleted": genres_deleted,
            "underrepresented_genres_deleted": 0,
            "invalid_name_genres_deleted": 0,
        }
    underrepresented_genres_deleted = await cleanup_underrepresented_genres(
        session, 5, batch_size, stop_check
    )
    if stop_check():
        return {
            "books": book_stats,
            "authors": author_stats,
            "series_deleted": series_deleted,
            "genres_deleted": genres_deleted,
            "underrepresented_genres_deleted": underrepresented_genres_deleted,
            "invalid_name_genres_deleted": 0,
        }
    invalid_name_genres_deleted = await cleanup_invalid_genre_names(
        session, batch_size, stop_check
    )

    return {
        "books": book_stats,
        "authors": author_stats,
        "series_deleted": series_deleted,
        "genres_deleted": genres_deleted,
        "underrepresented_genres_deleted": underrepresented_genres_deleted,
        "invalid_name_genres_deleted": invalid_name_genres_deleted,
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
            f"{stats['genres_deleted']} orphan genres, "
            f"{stats['underrepresented_genres_deleted']} underrepresented genres, "
            f"{stats['invalid_name_genres_deleted']} invalid name genres deleted"
        )

    except Exception as e:
        logger.error(f"[cleanup] Cleanup cycle failed: {str(e)}")
    finally:
        if redis_client is not None:
            redis_client.close()
