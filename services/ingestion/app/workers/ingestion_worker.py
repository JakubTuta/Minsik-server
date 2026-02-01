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
                    await _process_single_book(session, book_data)
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


async def _process_single_book(session, book_data: typing.Dict[str, typing.Any]):
    book_title = book_data.get("title")
    book_language = book_data.get("language")
    book_slug = book_data.get("slug")

    result = await session.execute(
        sqlalchemy.select(app.models.Book).where(
            app.models.Book.language == book_language,
            app.models.Book.slug == book_slug
        )
    )
    existing_book = result.scalar_one_or_none()

    if existing_book:
        await _update_existing_book(session, existing_book, book_data)
    else:
        await _create_new_book(session, book_data)


async def _create_new_book(session, book_data: typing.Dict[str, typing.Any]):
    author_ids = []
    for author_data in book_data.get("authors", []):
        author_id = await _get_or_create_author(session, author_data)
        if author_id:
            author_ids.append(author_id)

    genre_ids = []
    for genre_data in book_data.get("genres", []):
        genre_id = await _get_or_create_genre(session, genre_data)
        if genre_id:
            genre_ids.append(genre_id)

    book = app.models.Book(
        title=book_data.get("title"),
        language=book_data.get("language"),
        slug=book_data.get("slug"),
        description=book_data.get("description"),
        original_publication_year=book_data.get("original_publication_year"),
        formats=book_data.get("formats", []),
        cover_history=book_data.get("cover_history", []),
        primary_cover_url=book_data.get("primary_cover_url"),
        open_library_id=book_data.get("open_library_id"),
        google_books_id=book_data.get("google_books_id"),
        ts_vector=sqlalchemy.func.to_tsvector('english', book_data.get("title"))
    )

    session.add(book)
    await session.flush()

    for author_id in author_ids:
        book_author = app.models.BookAuthor(book_id=book.book_id, author_id=author_id)
        session.add(book_author)

    for genre_id in genre_ids:
        book_genre = app.models.BookGenre(book_id=book.book_id, genre_id=genre_id)
        session.add(book_genre)


async def _update_existing_book(session, existing_book: app.models.Book, book_data: typing.Dict[str, typing.Any]):
    existing_formats = set(existing_book.formats or [])
    new_formats = set(book_data.get("formats", []))
    merged_formats = list(existing_formats | new_formats)

    existing_covers = existing_book.cover_history or []
    new_covers = book_data.get("cover_history", [])

    cover_map = {cover["year"]: cover for cover in existing_covers}
    for new_cover in new_covers:
        year = new_cover["year"]
        if year not in cover_map:
            cover_map[year] = new_cover

    merged_cover_history = sorted(cover_map.values(), key=lambda x: x["year"])

    existing_book.formats = merged_formats
    existing_book.cover_history = merged_cover_history
    existing_book.updated_at = datetime.datetime.now()

    if not existing_book.description and book_data.get("description"):
        existing_book.description = book_data.get("description")

    if not existing_book.open_library_id and book_data.get("open_library_id"):
        existing_book.open_library_id = book_data.get("open_library_id")

    if not existing_book.google_books_id and book_data.get("google_books_id"):
        existing_book.google_books_id = book_data.get("google_books_id")


async def _get_or_create_author(session, author_data: typing.Dict[str, typing.Any]) -> typing.Optional[int]:
    if not author_data.get("name"):
        return None

    author_slug = author_data.get("slug")

    result = await session.execute(
        sqlalchemy.select(app.models.Author).where(app.models.Author.slug == author_slug)
    )
    existing_author = result.scalar_one_or_none()

    if existing_author:
        return existing_author.author_id

    author = app.models.Author(
        name=author_data.get("name"),
        slug=author_slug,
        bio=author_data.get("bio"),
        birth_date=author_data.get("birth_date"),
        death_date=author_data.get("death_date"),
        photo_url=author_data.get("photo_url"),
        open_library_id=author_data.get("open_library_id")
    )

    session.add(author)
    await session.flush()

    return author.author_id


async def _get_or_create_genre(session, genre_data: typing.Dict[str, typing.Any]) -> typing.Optional[int]:
    if not genre_data.get("name"):
        return None

    genre_slug = genre_data.get("slug")

    result = await session.execute(
        sqlalchemy.select(app.models.Genre).where(app.models.Genre.slug == genre_slug)
    )
    existing_genre = result.scalar_one_or_none()

    if existing_genre:
        return existing_genre.genre_id

    genre = app.models.Genre(
        name=genre_data.get("name"),
        slug=genre_slug
    )

    session.add(genre)
    await session.flush()

    return genre.genre_id


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
