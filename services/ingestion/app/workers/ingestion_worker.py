import asyncio
import logging
import typing
import datetime
import sqlalchemy
import sqlalchemy.dialects.postgresql
import redis
import json

import app.config
import app.models
import app.fetchers
import app.utils
import app.services.book_service

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
    host=app.config.settings.redis_host,
    port=app.config.settings.redis_port,
    db=app.config.settings.redis_db,
    password=app.config.settings.redis_password if app.config.settings.redis_password else None,
    decode_responses=True
)


async def process_ingestion_job(job_id: str, total_books: int, source: str, language: str = "en"):
    try:
        await _update_job_status(job_id, "running", 0, total_books)

        books_data = []

        if source == "both":
            books_per_source = total_books // 2

            async with app.fetchers.OpenLibraryFetcher() as ol_fetcher:
                ol_books = await ol_fetcher.fetch_books(books_per_source, language)
                books_data.extend(ol_books)

            async with app.fetchers.GoogleBooksFetcher() as gb_fetcher:
                gb_books = await gb_fetcher.fetch_books(books_per_source, language)
                books_data.extend(gb_books)

        elif source == "open_library":
            async with app.fetchers.OpenLibraryFetcher() as ol_fetcher:
                books_data = await ol_fetcher.fetch_books(total_books, language)

        elif source == "google_books":
            async with app.fetchers.GoogleBooksFetcher() as gb_fetcher:
                books_data = await gb_fetcher.fetch_books(total_books, language)

        else:
            raise ValueError(f"Invalid source: {source}")

        processed = 0
        successful = 0
        failed = 0

        async with app.models.AsyncSessionLocal() as session:
            for book_data in books_data:
                try:
                    await app.services.book_service.process_single_book(session, book_data)
                    await session.commit()
                    successful += 1
                except Exception as e:
                    logger.error(f"Book processing error: {str(e)}")
                    await session.rollback()
                    failed += 1

                processed += 1

                if processed % 50 == 0:
                    await _update_job_status(job_id, "running", processed, total_books, successful, failed)

        await _update_job_status(job_id, "completed", processed, total_books, successful, failed)

    except Exception as e:
        logger.error(f"Ingestion job failed: {str(e)}")
        await _update_job_status(job_id, "failed", 0, total_books, error=str(e))
        raise


async def _update_job_status(
    job_id: str,
    status: str,
    processed: int,
    total: int,
    successful: int = 0,
    failed: int = 0,
    error: typing.Optional[str] = None
):
    job_data = {
        "job_id": job_id,
        "status": status,
        "processed": processed,
        "total": total,
        "successful": successful,
        "failed": failed,
        "error": error,
        "started_at": int(datetime.datetime.now().timestamp()) if status == "running" else None,
        "completed_at": int(datetime.datetime.now().timestamp()) if status in ["completed", "failed"] else None
    }

    redis_client.setex(
        f"ingestion_job:{job_id}",
        3600,
        json.dumps(job_data)
    )


def run_ingestion_job_sync(job_id: str, total_books: int, source: str, language: str = "en"):
    asyncio.run(process_ingestion_job(job_id, total_books, source, language))
