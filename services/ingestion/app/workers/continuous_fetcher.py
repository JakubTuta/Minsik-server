import logging
import time

import app.config
import app.workers.ingestion_worker
import redis

logger = logging.getLogger(__name__)

_OL_OFFSET_KEY = "ingestion_ol_offset"
_GB_OFFSET_KEY = "ingestion_gb_offset"


def _create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=app.config.settings.redis_host,
        port=app.config.settings.redis_port,
        db=app.config.settings.redis_db,
        password=(
            app.config.settings.redis_password
            if app.config.settings.redis_password
            else None
        ),
        decode_responses=True,
    )


async def _run_continuous_fetch(label: str, source: str, offset_key: str, count: int) -> None:
    if not app.config.settings.continuous_fetch_enabled:
        return

    try:
        redis_client = _create_redis_client()
    except Exception as e:
        logger.error(f"Failed to connect to Redis for {label} fetch: {e}")
        return

    if redis_client.get("dump_import_running"):
        logger.info(f"Skipping {label} fetch cycle: dump import in progress")
        redis_client.close()
        return

    try:
        offset = int(redis_client.get(offset_key) or 0)
        job_id = f"continuous_{label.lower()}_{int(time.time())}"

        logger.info(f"Starting continuous {label} fetch: {count} books at offset {offset}")
        result = await app.workers.ingestion_worker.process_ingestion_job(
            job_id, count, source, "en", offset
        )

        redis_client.set(offset_key, offset + count)
        logger.info(
            f"Continuous {label} fetch done: {result['processed']} processed, {result['successful']} successful, {result['failed']} failed"
        )

    except Exception as e:
        logger.error(f"Continuous {label} fetch failed: {str(e)}")
    finally:
        try:
            redis_client.close()
        except Exception:
            pass


async def run_continuous_ol_fetch() -> None:
    await _run_continuous_fetch(
        "OL", "open_library", _OL_OFFSET_KEY, app.config.settings.continuous_ol_books_per_run
    )


async def run_continuous_gb_fetch() -> None:
    await _run_continuous_fetch(
        "GB", "google_books", _GB_OFFSET_KEY, app.config.settings.continuous_gb_books_per_run
    )
