import asyncio
import logging
import typing

import app.config
import app.models
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

_DUMP_RUNNING_KEY = "dump_import_running"
_BUBBLE_RUNNING_KEY = "genre_bubble_running"
_BUBBLE_RUNNING_TTL = 3600

SessionFactory = sqlalchemy.ext.asyncio.async_sessionmaker


def _create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=app.config.settings.redis_host,
        port=app.config.settings.redis_port,
        db=app.config.settings.redis_db,
        password=app.config.settings.redis_password or None,
        decode_responses=True,
    )


async def rebuild_genre_co_occurrences(
    session_factory: SessionFactory,
    min_pair_count: int = 5,
) -> int:
    try:
        async with session_factory() as session:
            await session.execute(
                sqlalchemy.text("TRUNCATE TABLE books.genre_co_occurrences")
            )

            result = await session.execute(
                sqlalchemy.text(
                    """
                    WITH work_genres AS (
                        -- Genres are copied to every language edition of a work
                        -- (see ingestion editions.py), so without collapsing to
                        -- one row per (work, genre) a heavily-translated work
                        -- would inflate both the pair count and the genre size
                        -- once per edition, skewing the Jaccard strength.
                        SELECT DISTINCT b.work_id, bg.genre_id
                        FROM books.book_genres bg
                        JOIN books.books b ON b.book_id = bg.book_id
                    ),
                    pair_counts AS (
                        SELECT
                            LEAST(wg1.genre_id, wg2.genre_id)    AS genre_id_a,
                            GREATEST(wg1.genre_id, wg2.genre_id) AS genre_id_b,
                            COUNT(*)                             AS co_count
                        FROM work_genres wg1
                        JOIN work_genres wg2
                            ON  wg1.work_id  = wg2.work_id
                            AND wg1.genre_id != wg2.genre_id
                        GROUP BY 1, 2
                        HAVING COUNT(*) >= :min_pair_count
                    ),
                    genre_sizes AS (
                        SELECT genre_id, COUNT(*) AS n
                        FROM work_genres
                        GROUP BY genre_id
                    )
                    INSERT INTO books.genre_co_occurrences
                        (genre_id_a, genre_id_b, co_occurrence_count, strength, updated_at)
                    SELECT
                        pc.genre_id_a,
                        pc.genre_id_b,
                        pc.co_count::INT,
                        pc.co_count::REAL / (ga.n + gb.n - pc.co_count),
                        NOW()
                    FROM pair_counts pc
                    JOIN genre_sizes ga ON ga.genre_id = pc.genre_id_a
                    JOIN genre_sizes gb ON gb.genre_id = pc.genre_id_b
                    """
                ),
                {"min_pair_count": min_pair_count},
            )

            inserted = result.rowcount
            await session.commit()

        logger.info(f"[genre_bubble] Rebuilt co-occurrences: {inserted} pairs")
        return inserted

    except Exception as e:
        logger.error(f"[genre_bubble] rebuild_genre_co_occurrences failed: {e}")
        return 0


async def run_genre_bubble_job(force: bool = False) -> None:
    if not force and not app.config.settings.genre_bubble_enabled:
        return

    redis_client: typing.Optional[redis.Redis] = None
    try:
        redis_client = _create_redis_client()
    except Exception as e:
        logger.warning(f"[genre_bubble] Failed to connect to Redis: {e}")

    try:
        if redis_client is not None and redis_client.get(_DUMP_RUNNING_KEY):
            logger.info("[genre_bubble] Skipping: dump import in progress")
            return

        if redis_client is not None:
            redis_client.set(_BUBBLE_RUNNING_KEY, "1", ex=_BUBBLE_RUNNING_TTL)

        min_pair_count = app.config.settings.genre_bubble_min_pair_count
        await rebuild_genre_co_occurrences(app.models.AsyncSessionLocal, min_pair_count)

    except Exception as e:
        logger.error(f"[genre_bubble] Job failed: {e}")
    finally:
        if redis_client is not None:
            try:
                redis_client.delete(_BUBBLE_RUNNING_KEY)
            except Exception:
                pass
            redis_client.close()
