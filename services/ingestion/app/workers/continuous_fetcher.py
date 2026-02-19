import asyncio
import logging
import time
import typing

import app.config
import app.workers.ingestion_worker
import redis

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
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

_OL_OFFSET_KEY = "ingestion_ol_offset"
_GB_OFFSET_KEY = "ingestion_gb_offset"


async def run_continuous_ol_fetch(shutdown_event: asyncio.Event) -> None:
    logger.info("Continuous Open Library fetch task started")
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(app.config.settings.continuous_ol_interval_hours * 3600)
        except asyncio.CancelledError:
            break

        if shutdown_event.is_set() or not app.config.settings.continuous_fetch_enabled:
            break

        if redis_client.get("dump_import_running"):
            logger.info("Skipping OL fetch cycle: dump import in progress")
            continue

        try:
            offset = int(redis_client.get(_OL_OFFSET_KEY) or 0)
            job_id = f"continuous_ol_{int(time.time())}"
            count = app.config.settings.continuous_ol_books_per_run

            logger.info(
                f"Starting continuous OL fetch: {count} books at offset {offset}"
            )
            result = await app.workers.ingestion_worker.process_ingestion_job(
                job_id, count, "open_library", "en", offset
            )

            redis_client.set(_OL_OFFSET_KEY, offset + count)
            logger.info(
                f"Continuous OL fetch done: {result['processed']} processed, {result['successful']} successful, {result['failed']} failed"
            )

        except Exception as e:
            logger.error(f"Continuous OL fetch failed: {str(e)}")

    logger.info("Continuous Open Library fetch task stopped")


async def run_continuous_gb_fetch(shutdown_event: asyncio.Event) -> None:
    logger.info("Continuous Google Books fetch task started")
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(app.config.settings.continuous_gb_interval_hours * 3600)
        except asyncio.CancelledError:
            break

        if shutdown_event.is_set() or not app.config.settings.continuous_fetch_enabled:
            break

        if redis_client.get("dump_import_running"):
            logger.info("Skipping GB fetch cycle: dump import in progress")
            continue

        try:
            offset = int(redis_client.get(_GB_OFFSET_KEY) or 0)
            job_id = f"continuous_gb_{int(time.time())}"
            count = app.config.settings.continuous_gb_books_per_run

            logger.info(
                f"Starting continuous GB fetch: {count} books at offset {offset}"
            )
            result = await app.workers.ingestion_worker.process_ingestion_job(
                job_id, count, "google_books", "en", offset
            )

            redis_client.set(_GB_OFFSET_KEY, offset + count)
            logger.info(
                f"Continuous GB fetch done: {result['processed']} processed, {result['successful']} successful, {result['failed']} failed"
            )

        except Exception as e:
            logger.error(f"Continuous GB fetch failed: {str(e)}")

    logger.info("Continuous Google Books fetch task stopped")
