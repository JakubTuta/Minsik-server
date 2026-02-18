import asyncio
import logging
import typing

import app.config
import app.models
import app.fetchers
import app.services.book_service

logger = logging.getLogger(__name__)


async def process_ingestion_job(
    job_id: str,
    total_books: int,
    source: str,
    language: str = "en",
    offset: int = 0
) -> typing.Dict[str, typing.Any]:
    try:
        books_data = []

        if source == "both":
            books_per_source = total_books // 2

            async with app.fetchers.OpenLibraryFetcher() as ol_fetcher:
                ol_books = await ol_fetcher.fetch_books(books_per_source, language, offset)
                books_data.extend(ol_books)

            async with app.fetchers.GoogleBooksFetcher() as gb_fetcher:
                gb_books = await gb_fetcher.fetch_books(books_per_source, language, offset)
                books_data.extend(gb_books)

        elif source == "open_library":
            async with app.fetchers.OpenLibraryFetcher() as ol_fetcher:
                books_data = await ol_fetcher.fetch_books(total_books, language, offset)

        elif source == "google_books":
            async with app.fetchers.GoogleBooksFetcher() as gb_fetcher:
                books_data = await gb_fetcher.fetch_books(total_books, language, offset)

        else:
            raise ValueError(f"Invalid source: {source}")

        if not books_data:
            return {
                "processed": 0,
                "successful": 0,
                "failed": 0,
                "error": None
            }

        batch_size = 1000
        processed = 0
        successful = 0
        failed = 0

        async with app.models.AsyncSessionLocal() as session:
            try:
                for batch_start in range(0, len(books_data), batch_size):
                    batch = books_data[batch_start:batch_start + batch_size]

                    try:
                        result = await app.services.book_service.insert_books_batch(session, batch, commit=True)
                        successful += result["successful"]
                        failed += result["failed"]
                        processed += len(batch)
                    except Exception as e:
                        logger.error(f"Batch processing error: {str(e)}")
                        await session.rollback()
                        failed += len(batch)
                        processed += len(batch)

            except Exception as e:
                logger.error(f"Ingestion job {job_id} failed during batch processing: {str(e)}")
                await session.rollback()
                raise

        logger.info(f"Ingestion job {job_id} completed: {processed} processed, {successful} successful, {failed} failed")

        return {
            "processed": processed,
            "successful": successful,
            "failed": failed,
            "error": None
        }

    except Exception as e:
        logger.error(f"Ingestion job {job_id} failed: {str(e)}")
        return {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "error": str(e)
        }
