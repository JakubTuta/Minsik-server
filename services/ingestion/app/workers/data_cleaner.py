import asyncio
import logging
import typing

import app.config
import app.models
import app.utils
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy.engine import CursorResult

logger = logging.getLogger(__name__)

_DUMP_RUNNING_KEY = "dump_import_running"
_SOLE_BOOK_SUB_BATCH = 100

SessionFactory = sqlalchemy.ext.asyncio.async_sessionmaker


def _create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=app.config.settings.redis_host,
        port=app.config.settings.redis_port,
        db=app.config.settings.redis_db,
        password=app.config.settings.redis_password or None,
        decode_responses=True,
    )


async def _delete_book_user_data(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    book_ids: typing.List[int],
) -> typing.List[int]:
    if not book_ids:
        return []

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
        {"book_ids": book_ids},
    )
    affected_user_ids = [row[0] for row in affected_users_result.fetchall()]

    await session.execute(
        sqlalchemy.text("DELETE FROM user_data.comments WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )
    await session.execute(
        sqlalchemy.text("DELETE FROM user_data.ratings WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )
    await session.execute(
        sqlalchemy.text("DELETE FROM user_data.bookshelves WHERE book_id = ANY(:book_ids)"),
        {"book_ids": book_ids},
    )

    return affected_user_ids


async def _recompute_user_stats(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_ids: typing.List[int],
) -> None:
    for user_id in user_ids:
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


async def cleanup_low_quality_books(
    session_factory: SessionFactory,
    min_quality_score: int,
    engagement_threshold: int,
    min_publication_year: int,
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

    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping book cleanup: dump import started")
            break
        deleted = 0
        try:
            async with session_factory() as session:
                id_result = await session.execute(
                    sqlalchemy.text(
                        f"""
                        SELECT b.book_id FROM books.books b
                        WHERE b.created_at < NOW() - INTERVAL '1 day'
                          AND b.view_count <= 2
                          AND (
                            (
                              ({quality_score_sql}) < :min_score
                              AND (b.rating_count + COALESCE(b.ol_rating_count, 0)) < :engagement
                              AND (
                                COALESCE(b.ol_already_read_count, 0) +
                                (SELECT COUNT(*) FROM user_data.bookshelves bs WHERE bs.book_id = b.book_id)
                              ) < :engagement
                            )
                            OR NOT EXISTS (SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id)
                            OR b.title ~ '^[\\s\\W]*$'
                            OR char_length(btrim(b.title)) < 2
                            OR b.original_publication_year > EXTRACT(YEAR FROM NOW())::int + 1
                            OR b.original_publication_year < :min_year
                            OR (
                              NOT EXISTS (SELECT 1 FROM books.book_genres bg WHERE bg.book_id = b.book_id)
                              AND ({quality_score_sql}) < 5
                            )
                          )
                        LIMIT :batch_size
                        """
                    ),
                    {
                        "min_score": min_quality_score,
                        "engagement": engagement_threshold,
                        "min_year": min_publication_year,
                        "batch_size": batch_size,
                    },
                )
                book_ids = [row[0] for row in id_result.fetchall()]

                if not book_ids:
                    break

                affected_user_ids = await _delete_book_user_data(session, book_ids)
                result = await session.execute(
                    sqlalchemy.text("DELETE FROM books.books WHERE book_id = ANY(:book_ids)"),
                    {"book_ids": book_ids},
                )
                deleted = typing.cast(CursorResult, result).rowcount
                await _recompute_user_stats(session, affected_user_ids)
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Book cleanup batch failed: {e}")
            break

        if deleted == 0:
            break

        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} low-quality books so far")
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted}


async def cleanup_duplicate_books(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping duplicate book cleanup: dump import started")
            break
        deleted = 0
        try:
            async with session_factory() as session:
                id_result = await session.execute(
                    sqlalchemy.text(
                        """
                        WITH ranked AS (
                            SELECT
                                b.book_id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY
                                        lower(btrim(b.title)),
                                        b.language,
                                        (SELECT MIN(ba.author_id)
                                         FROM books.book_authors ba
                                         WHERE ba.book_id = b.book_id)
                                    ORDER BY
                                        (b.view_count + b.rating_count + COALESCE(b.ol_rating_count, 0)) DESC,
                                        b.book_id ASC
                                ) AS rn
                            FROM books.books b
                            WHERE EXISTS (
                                SELECT 1 FROM books.book_authors ba WHERE ba.book_id = b.book_id
                            )
                        )
                        SELECT book_id FROM ranked WHERE rn > 1
                        LIMIT :batch_size
                        """
                    ),
                    {"batch_size": batch_size},
                )
                book_ids = [row[0] for row in id_result.fetchall()]

                if not book_ids:
                    break

                affected_user_ids = await _delete_book_user_data(session, book_ids)
                result = await session.execute(
                    sqlalchemy.text("DELETE FROM books.books WHERE book_id = ANY(:book_ids)"),
                    {"book_ids": book_ids},
                )
                deleted = typing.cast(CursorResult, result).rowcount
                await _recompute_user_stats(session, affected_user_ids)
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Duplicate book cleanup batch failed: {e}")
            break

        if deleted == 0:
            break

        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} duplicate books so far")
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted}


async def cleanup_orphan_authors(
    session_factory: SessionFactory,
    min_books: int,
    max_books: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, int]:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping author cleanup: dump import started")
            break

        deleted = 0
        try:
            async with session_factory() as session:
                author_id_result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT a.author_id FROM books.authors a
                        LEFT JOIN (
                            SELECT author_id, COUNT(*) AS book_count
                            FROM books.book_authors
                            GROUP BY author_id
                        ) ba ON ba.author_id = a.author_id
                        WHERE COALESCE(ba.book_count, 0) < :min_books
                           OR COALESCE(ba.book_count, 0) > :max_books
                           OR a.name !~ '[A-Za-z]'
                           OR char_length(btrim(a.name)) < 2
                        LIMIT :batch_size
                        """
                    ),
                    {"min_books": min_books, "max_books": max_books, "batch_size": batch_size},
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
                sole_book_ids = [row[0] for row in book_id_result.fetchall() if row[1] == 1]

                for i in range(0, len(sole_book_ids), _SOLE_BOOK_SUB_BATCH):
                    sub_batch = sole_book_ids[i : i + _SOLE_BOOK_SUB_BATCH]
                    affected_user_ids = await _delete_book_user_data(session, sub_batch)
                    await session.execute(
                        sqlalchemy.text(
                            "DELETE FROM books.books WHERE book_id = ANY(:book_ids)"
                        ),
                        {"book_ids": sub_batch},
                    )
                    await _recompute_user_stats(session, affected_user_ids)

                result = await session.execute(
                    sqlalchemy.text(
                        "DELETE FROM books.authors WHERE author_id = ANY(:author_ids)"
                    ),
                    {"author_ids": author_ids},
                )
                deleted = typing.cast(CursorResult, result).rowcount
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Author cleanup batch failed: {e}")
            break

        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} low-relevance authors so far")
        await asyncio.sleep(0.5)

    return {"deleted": total_deleted}


async def cleanup_underrepresented_series(
    session_factory: SessionFactory,
    min_books: int,
    max_books: int,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping series cleanup: dump import started")
            break

        deleted = 0
        try:
            async with session_factory() as session:
                series_id_result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT s.series_id
                        FROM books.series s
                        LEFT JOIN (
                            SELECT series_id, COUNT(*) AS book_count
                            FROM books.books
                            WHERE series_id IS NOT NULL
                            GROUP BY series_id
                        ) bc ON bc.series_id = s.series_id
                        WHERE COALESCE(bc.book_count, 0) < :min_books
                           OR COALESCE(bc.book_count, 0) > :max_books
                           OR s.name !~ '[A-Za-z]'
                           OR char_length(btrim(s.name)) < 2
                        LIMIT :batch_size
                        """
                    ),
                    {"min_books": min_books, "max_books": max_books, "batch_size": batch_size},
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
        except Exception as e:
            logger.error(f"[cleanup] Series cleanup batch failed: {e}")
            break

        total_deleted += deleted
        logger.info(f"[cleanup] Deleted {total_deleted} series so far")
        await asyncio.sleep(0.5)

    return total_deleted


async def normalize_and_merge_genres(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_merged = 0
    offset = 0

    while True:
        if stop_check():
            logger.info("[cleanup] Stopping genre normalization: dump import started")
            break

        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        "SELECT genre_id, name, slug FROM books.genres ORDER BY genre_id LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": batch_size, "offset": offset},
                )
                rows = result.fetchall()
        except Exception as e:
            logger.error(f"[cleanup] Genre normalization fetch failed: {e}")
            break

        if not rows:
            break

        for row in rows:
            old_id: int = row[0]
            current_name: str = row[1]
            current_slug: str = row[2]

            canonical_name, canonical_slug = app.utils.canonicalize_genre_name(
                current_name
            )

            if canonical_slug == current_slug:
                continue

            try:
                async with session_factory() as session:
                    canonical_result = await session.execute(
                        sqlalchemy.text(
                            "SELECT genre_id FROM books.genres WHERE slug = :slug"
                        ),
                        {"slug": canonical_slug},
                    )
                    canonical_row = canonical_result.fetchone()

                    if canonical_row:
                        canonical_id = canonical_row[0]
                        if canonical_id == old_id:
                            continue
                        await session.execute(
                            sqlalchemy.text(
                                """
                                INSERT INTO books.book_genres (book_id, genre_id)
                                SELECT book_id, :canonical_id FROM books.book_genres
                                WHERE genre_id = :old_id
                                ON CONFLICT DO NOTHING
                                """
                            ),
                            {"canonical_id": canonical_id, "old_id": old_id},
                        )
                        await session.execute(
                            sqlalchemy.text(
                                "DELETE FROM books.book_genres WHERE genre_id = :old_id"
                            ),
                            {"old_id": old_id},
                        )
                        await session.execute(
                            sqlalchemy.text(
                                "DELETE FROM books.genres WHERE genre_id = :old_id"
                            ),
                            {"old_id": old_id},
                        )
                    else:
                        await session.execute(
                            sqlalchemy.text(
                                "UPDATE books.genres SET name = :name, slug = :slug WHERE genre_id = :id"
                            ),
                            {
                                "name": canonical_name[:100],
                                "slug": canonical_slug[:150],
                                "id": old_id,
                            },
                        )

                    await session.commit()
                    total_merged += 1
            except Exception as e:
                logger.error(
                    f"[cleanup] Genre normalization merge failed for genre_id={old_id}: {e}"
                )

        offset += batch_size
        await asyncio.sleep(0.1)

    logger.info(f"[cleanup] Genre normalization complete. Merged/renamed: {total_merged}")
    return total_merged


async def cleanup_orphan_genres(
    session_factory: SessionFactory,
    batch_size: int,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> int:
    total_deleted = 0
    while True:
        if stop_check():
            logger.info("[cleanup] Stopping genre cleanup: dump import started")
            break
        deleted = 0
        try:
            async with session_factory() as session:
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
        except Exception as e:
            logger.error(f"[cleanup] Orphan genre cleanup batch failed: {e}")
            break

        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def cleanup_underrepresented_genres(
    session_factory: SessionFactory,
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
        deleted = 0
        try:
            async with session_factory() as session:
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
        except Exception as e:
            logger.error(f"[cleanup] Underrepresented genre cleanup batch failed: {e}")
            break

        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def cleanup_invalid_genre_names(
    session_factory: SessionFactory,
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
        deleted = 0
        try:
            async with session_factory() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        """
                        DELETE FROM books.genres
                        WHERE genre_id IN (
                            SELECT g.genre_id FROM books.genres g
                            WHERE g.name ~ '[^a-zA-Z0-9 -]'
                               OR g.name ~ '^[0-9]+$'
                               OR char_length(g.name) > 40
                            LIMIT :batch_size
                        )
                        """
                    ),
                    {"batch_size": batch_size},
                )
                deleted = typing.cast(CursorResult, result).rowcount
                await session.commit()
        except Exception as e:
            logger.error(f"[cleanup] Invalid genre name cleanup batch failed: {e}")
            break

        if deleted == 0:
            break

        total_deleted += deleted
        await asyncio.sleep(0.5)

    return total_deleted


async def run_cleanup_cycle(
    session_factory: SessionFactory,
    stop_check: typing.Callable[[], bool] = lambda: False,
) -> typing.Dict[str, typing.Any]:
    book_batch = app.config.settings.cleanup_book_batch_size
    author_batch = app.config.settings.cleanup_author_batch_size
    series_batch = app.config.settings.cleanup_series_batch_size
    genre_batch = app.config.settings.cleanup_genre_batch_size
    min_quality = app.config.settings.cleanup_book_min_quality_score
    engagement_threshold = app.config.settings.cleanup_book_engagement_threshold
    min_publication_year = app.config.settings.cleanup_book_min_publication_year
    genre_min_book_count = app.config.settings.cleanup_genre_min_book_count
    min_author_books = app.config.settings.cleanup_author_min_books
    max_author_books = app.config.settings.cleanup_author_max_books
    min_series_books = app.config.settings.cleanup_series_min_books
    max_series_books = app.config.settings.cleanup_series_max_books

    stats: typing.Dict[str, typing.Any] = {
        "books": {"deleted": 0},
        "duplicates": {"deleted": 0},
        "authors": {"deleted": 0},
        "series_deleted": 0,
        "genres_normalized": 0,
        "genres_deleted": 0,
        "underrepresented_genres_deleted": 0,
        "invalid_name_genres_deleted": 0,
    }

    stats["books"] = await cleanup_low_quality_books(
        session_factory,
        min_quality,
        engagement_threshold,
        min_publication_year,
        book_batch,
        stop_check,
    )
    if stop_check():
        return stats

    stats["duplicates"] = await cleanup_duplicate_books(
        session_factory, book_batch, stop_check
    )
    if stop_check():
        return stats

    stats["authors"] = await cleanup_orphan_authors(
        session_factory, min_author_books, max_author_books, author_batch, stop_check
    )
    if stop_check():
        return stats

    stats["series_deleted"] = await cleanup_underrepresented_series(
        session_factory, min_series_books, max_series_books, series_batch, stop_check
    )
    if stop_check():
        return stats

    stats["genres_normalized"] = await normalize_and_merge_genres(
        session_factory, genre_batch, stop_check
    )
    if stop_check():
        return stats

    stats["genres_deleted"] = await cleanup_orphan_genres(
        session_factory, genre_batch, stop_check
    )
    if stop_check():
        return stats

    stats["underrepresented_genres_deleted"] = await cleanup_underrepresented_genres(
        session_factory, genre_min_book_count, genre_batch, stop_check
    )
    if stop_check():
        return stats

    stats["invalid_name_genres_deleted"] = await cleanup_invalid_genre_names(
        session_factory, genre_batch, stop_check
    )

    return stats


_CLEANUP_RUNNING_KEY = "cleanup_running"
_CLEANUP_RUNNING_TTL = 7200


async def run_cleanup_job(force: bool = False) -> None:
    if not force and not app.config.settings.cleanup_enabled:
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

        if redis_client is not None:
            redis_client.set(_CLEANUP_RUNNING_KEY, "1", ex=_CLEANUP_RUNNING_TTL)

        def stop_check() -> bool:
            if redis_client is None:
                return False
            try:
                return bool(redis_client.get(_DUMP_RUNNING_KEY))
            except Exception:
                return False

        stats = await run_cleanup_cycle(app.models.AsyncSessionLocal, stop_check)

        logger.info(
            f"[cleanup] Cycle complete: "
            f"{stats['books']['deleted']} books, "
            f"{stats['duplicates']['deleted']} duplicate books, "
            f"{stats['authors']['deleted']} authors, "
            f"{stats['series_deleted']} series, "
            f"{stats['genres_normalized']} genres normalized, "
            f"{stats['genres_deleted']} orphan genres, "
            f"{stats['underrepresented_genres_deleted']} underrepresented genres, "
            f"{stats['invalid_name_genres_deleted']} invalid name genres deleted"
        )

    except Exception as e:
        logger.error(f"[cleanup] Cleanup cycle failed: {str(e)}")
    finally:
        if redis_client is not None:
            try:
                redis_client.delete(_CLEANUP_RUNNING_KEY)
            except Exception:
                pass
            redis_client.close()
