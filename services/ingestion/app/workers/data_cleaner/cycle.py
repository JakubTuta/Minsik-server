import logging
import typing

import app.config
import app.models
import app.workers.data_cleaner.authors as authors
import app.workers.data_cleaner.books as books
import app.workers.data_cleaner.genres as genres
import app.workers.data_cleaner.names as names
import app.workers.data_cleaner.runtime as runtime
import app.workers.data_cleaner.series as series
import redis

logger = logging.getLogger(__name__)

_CLEANUP_RUNNING_KEY = "cleanup_running"
_CLEANUP_RUNNING_TTL = 7200


async def run_cleanup_cycle(
    session_factory: runtime.SessionFactory,
    stop_check: runtime.StopCheck = runtime.never_stop,
) -> typing.Dict[str, typing.Any]:
    settings = app.config.settings
    book_batch = settings.cleanup_book_batch_size
    author_batch = settings.cleanup_author_batch_size
    series_batch = settings.cleanup_series_batch_size
    genre_batch = settings.cleanup_genre_batch_size
    min_ol_engagement = settings.cleanup_ol_min_engagement

    stats: typing.Dict[str, typing.Any] = {}

    stats["names_healed"] = await names.heal_entity_names(
        session_factory, book_batch, stop_check
    )

    stats["books"] = await books.cleanup_low_quality_books(
        session_factory,
        settings.cleanup_book_min_quality_score,
        settings.cleanup_book_engagement_threshold,
        settings.cleanup_book_min_publication_year,
        settings.cleanup_book_max_title_length,
        settings.cleanup_book_ol_min_rating_count,
        settings.cleanup_book_ol_min_avg_rating,
        book_batch,
        stop_check,
    )

    stats["low_engagement_books"] = (
        await books.cleanup_low_engagement_books(
            session_factory, min_ol_engagement, book_batch, stop_check
        )
    )

    stats["multi_author_books"] = (
        await books.cleanup_multi_author_books(
            session_factory, settings.cleanup_book_max_authors, book_batch, stop_check
        )
    )

    if settings.cleanup_collection_entries:
        stats["collection_books"] = (
            await books.cleanup_collection_books(
                session_factory, book_batch, stop_check
            )
        )
        stats["collection_authors"] = (
            await authors.cleanup_collection_authors(
                session_factory, author_batch, stop_check
            )
        )

    stats["duplicates"] = await books.cleanup_duplicate_books(
        session_factory, book_batch, stop_check
    )

    stats["authors"] = await authors.cleanup_orphan_authors(
        session_factory,
        settings.cleanup_author_min_books,
        settings.cleanup_author_max_books,
        author_batch,
        settings.cleanup_author_junk_publisher_names,
        stop_check,
    )

    stats["low_engagement_authors"] = (
        await authors.cleanup_low_engagement_authors(
            session_factory, min_ol_engagement, author_batch, stop_check
        )
    )

    stats["series"] = await series.consolidate_series(
        session_factory,
        settings.cleanup_series_min_books,
        settings.cleanup_series_max_books,
        series_batch,
        min_ol_engagement,
        stop_check,
    )

    stats["genres_normalized"] = (
        await genres.normalize_and_merge_genres(
            session_factory, genre_batch, stop_check
        )
    )
    stats["junk_genres_deleted"] = (
        await genres.cleanup_junk_genres(
            session_factory, genre_batch, stop_check
        )
    )
    stats["invalid_name_genres_deleted"] = (
        await genres.cleanup_invalid_genre_names(
            session_factory, genre_batch, stop_check
        )
    )
    stats["underrepresented_genres_deleted"] = (
        await genres.cleanup_underrepresented_genres(
            session_factory, settings.cleanup_genre_min_book_count, genre_batch, stop_check
        )
    )
    stats["genres_deleted"] = await genres.cleanup_orphan_genres(
        session_factory, genre_batch, stop_check
    )

    return stats


async def run_cleanup_job(force: bool = False) -> None:
    if not force and not app.config.settings.cleanup_enabled:
        return

    redis_client: typing.Optional[redis.Redis] = None
    try:
        redis_client = runtime.create_redis_client()
    except Exception as e:
        logger.warning(f"[cleanup] Failed to connect to Redis: {e}")

    try:
        if redis_client is not None and redis_client.get(_CLEANUP_RUNNING_KEY):
            logger.info(
                "Skipping cleanup cycle: another cleanup cycle is already running"
            )
            return

        if redis_client is not None:
            redis_client.set(_CLEANUP_RUNNING_KEY, "1", ex=_CLEANUP_RUNNING_TTL)

        def stop_check() -> bool:
            if redis_client is None:
                return False
            try:
                return bool(
                    redis_client.get(runtime.DUMP_RUNNING_KEY)
                )
            except Exception:
                return False

        stats = await run_cleanup_cycle(app.models.AsyncSessionLocal, stop_check)

        logger.info(f"[cleanup] Cycle complete: {stats}")

    except Exception as e:
        logger.error(f"[cleanup] Cleanup cycle failed: {str(e)}")
    finally:
        if redis_client is not None:
            try:
                redis_client.delete(_CLEANUP_RUNNING_KEY)
            except Exception:
                pass
            redis_client.close()
