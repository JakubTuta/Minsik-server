import logging
import typing
from typing import Any, Dict, List, Optional

import app.config
import app.models.author
import app.models.book
import app.models.book_author
import app.models.book_genre
import app.models.genre
import app.models.series
import app.utils
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

logger = logging.getLogger(__name__)


async def get_db_session() -> sqlalchemy.ext.asyncio.AsyncSession:
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        app.config.settings.database_url,
        pool_size=app.config.settings.db_pool_size,
        max_overflow=app.config.settings.db_max_overflow,
        echo=False,
    )

    async_session = sqlalchemy.ext.asyncio.async_sessionmaker(
        engine, class_=sqlalchemy.ext.asyncio.AsyncSession, expire_on_commit=False
    )

    return async_session()


async def insert_books_batch(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    books_data: List[Dict[str, Any]],
    commit: bool = True,
) -> Dict[str, int]:
    if not books_data:
        return {"successful": 0, "failed": 0, "updated": 0}

    successful = 0
    failed = 0
    updated = 0

    try:
        cleaned_books = []
        for book_data in books_data:
            try:
                cleaned = _validate_and_clean_book(book_data)
                if cleaned:
                    cleaned_books.append(cleaned)
            except Exception as e:
                logger.debug(
                    f"Error cleaning book '{book_data.get('title')}': {str(e)}"
                )
                failed += 1

        if not cleaned_books:
            if commit:
                await session.commit()
            return {"successful": 0, "failed": failed, "updated": 0}

        dedup_cache = _build_dedup_cache(cleaned_books)

        author_id_map = await _bulk_insert_authors(session, cleaned_books, dedup_cache)
        genre_id_map = await _bulk_insert_genres(session, cleaned_books, dedup_cache)
        series_id_map = await _bulk_insert_series(session, cleaned_books, dedup_cache)

        book_results = await _bulk_insert_books(
            session, cleaned_books, dedup_cache, series_id_map
        )
        successful = book_results["inserted"]
        updated = book_results["updated"]

        await _bulk_insert_relationships(
            session,
            cleaned_books,
            dedup_cache,
            book_results["book_id_map"],
            author_id_map,
            genre_id_map,
        )

        await session.flush()

        if commit:
            await session.commit()

        return {"successful": successful, "failed": failed, "updated": updated}

    except Exception as e:
        logger.error(f"Error in insert_books_batch: {str(e)}")
        await session.rollback()
        raise


def _validate_and_clean_book(book_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = book_data.get("title")
    if not title or not isinstance(title, str):
        return None

    language = book_data.get("language", "en")
    if isinstance(language, str):
        language = language.lower()

    description = app.utils.clean_description(book_data.get("description"))
    slug = app.utils.slugify(title)

    series_name = None
    series_id = None
    series_position = None

    series_data = book_data.get("series")
    if series_data:
        series_name = series_data.get("name")
        series_id = None
        series_position = series_data.get("position")
        title = app.utils.format_title_with_series(title, series_name)

    formats = book_data.get("formats", [])
    formats = [fmt.lower() if isinstance(fmt, str) else fmt for fmt in formats]

    isbn = book_data.get("isbn", [])
    if not isinstance(isbn, list):
        isbn = []

    publisher = book_data.get("publisher")
    if isinstance(publisher, str):
        publisher = publisher[:500]
    else:
        publisher = None

    number_of_pages = book_data.get("number_of_pages")
    if not isinstance(number_of_pages, int) or number_of_pages <= 0:
        number_of_pages = None

    external_ids = book_data.get("external_ids", {})
    if not isinstance(external_ids, dict):
        external_ids = {}

    return {
        "title": title,
        "language": language,
        "slug": slug,
        "description": description,
        "original_publication_year": book_data.get("original_publication_year"),
        "primary_cover_url": book_data.get("primary_cover_url"),
        "open_library_id": book_data.get("open_library_id"),
        "google_books_id": book_data.get("google_books_id"),
        "series_data": series_data,
        "series_name": series_name,
        "formats": formats,
        "cover_history": book_data.get("cover_history", []),
        "isbn": isbn,
        "publisher": publisher,
        "number_of_pages": number_of_pages,
        "external_ids": external_ids,
        "authors": book_data.get("authors", []),
        "genres": book_data.get("genres", []),
    }


def _build_dedup_cache(cleaned_books: List[Dict[str, Any]]) -> Dict[str, Any]:
    cache = {"authors": {}, "genres": {}, "series": {}}

    for book in cleaned_books:
        for author_data in book.get("authors", []):
            author_slug = app.utils.slugify(author_data.get("name", ""))
            if author_slug and author_slug not in cache["authors"]:
                cache["authors"][author_slug] = author_data

        for genre_data in book.get("genres", []):
            genre_name = genre_data.get("name", "")
            if isinstance(genre_name, str):
                genre_name = genre_name.lower()
            genre_slug = app.utils.slugify(genre_name)
            if genre_slug and genre_slug not in cache["genres"]:
                cache["genres"][genre_slug] = {"name": genre_name, "slug": genre_slug}

        if book.get("series_data"):
            series_slug = app.utils.slugify(book["series_data"].get("name", ""))
            if series_slug and series_slug not in cache["series"]:
                cache["series"][series_slug] = book["series_data"]

    return cache


async def _bulk_insert_authors(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: List[Dict[str, Any]],
    dedup_cache: Dict[str, Any],
) -> Dict[str, int]:
    if not dedup_cache["authors"]:
        return {}

    insert_data = []
    for author_slug, author_data in dedup_cache["authors"].items():
        name = author_data.get("name")
        insert_data.append(
            {
                "name": name,
                "slug": author_slug,
                "bio": app.utils.clean_description(author_data.get("bio")),
                "birth_date": app.utils.parse_date(author_data.get("birth_date")),
                "death_date": app.utils.parse_date(author_data.get("death_date")),
                "photo_url": author_data.get("photo_url"),
                "open_library_id": author_data.get("open_library_id"),
                "wikidata_id": author_data.get("wikidata_id"),
                "wikipedia_url": author_data.get("wikipedia_url"),
                "remote_ids": author_data.get("remote_ids", {}),
                "alternate_names": author_data.get("alternate_names", []),
            }
        )

    stmt = postgresql_insert(app.models.author.Author).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"],
        set_={
            "bio": stmt.excluded.bio,
            "birth_date": stmt.excluded.birth_date,
            "death_date": stmt.excluded.death_date,
            "photo_url": stmt.excluded.photo_url,
            "open_library_id": stmt.excluded.open_library_id,
            "wikidata_id": stmt.excluded.wikidata_id,
            "wikipedia_url": stmt.excluded.wikipedia_url,
            "remote_ids": stmt.excluded.remote_ids,
            "alternate_names": stmt.excluded.alternate_names,
        },
    )

    await session.execute(stmt)

    author_slugs = list(dedup_cache["authors"].keys())
    query = sqlalchemy.select(app.models.author.Author).where(
        app.models.author.Author.slug.in_(author_slugs)
    )
    result = await session.execute(query)
    author_id_map = {row.slug: row.author_id for row in result}

    return author_id_map


async def _bulk_insert_genres(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: List[Dict[str, Any]],
    dedup_cache: Dict[str, Any],
) -> Dict[str, int]:
    if not dedup_cache["genres"]:
        return {}

    insert_data = list(dedup_cache["genres"].values())

    stmt = postgresql_insert(app.models.genre.Genre).values(insert_data)
    stmt = stmt.on_conflict_do_update(index_elements=["slug"], set_={})

    await session.execute(stmt)

    genre_slugs = list(dedup_cache["genres"].keys())
    query = sqlalchemy.select(app.models.genre.Genre).where(
        app.models.genre.Genre.slug.in_(genre_slugs)
    )
    result = await session.execute(query)
    genre_id_map = {row.slug: row.genre_id for row in result}

    return genre_id_map


async def _bulk_insert_series(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: List[Dict[str, Any]],
    dedup_cache: Dict[str, Any],
) -> Dict[str, int]:
    if not dedup_cache["series"]:
        return {}

    insert_data = []
    for series_slug, series_data in dedup_cache["series"].items():
        insert_data.append(
            {
                "name": series_data.get("name"),
                "slug": series_slug,
                "description": series_data.get("description"),
            }
        )

    stmt = postgresql_insert(app.models.series.Series).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["slug"], set_={"description": stmt.excluded.description}
    )

    await session.execute(stmt)

    series_slugs = list(dedup_cache["series"].keys())
    query = sqlalchemy.select(app.models.series.Series).where(
        app.models.series.Series.slug.in_(series_slugs)
    )
    result = await session.execute(query)
    series_id_map = {row.slug: row.series_id for row in result}

    return series_id_map


async def _bulk_insert_books(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: List[Dict[str, Any]],
    dedup_cache: Dict[str, Any],
    series_id_map: Dict[str, int],
) -> Dict[str, Any]:
    insert_data = []
    upsert_data = []

    for book in cleaned_books:
        series_id = None
        if book.get("series_data"):
            series_slug = app.utils.slugify(book["series_data"].get("name", ""))
            series_id = series_id_map.get(series_slug)

        book_entry = {
            "title": book["title"],
            "language": book["language"],
            "slug": book["slug"],
            "description": book["description"],
            "original_publication_year": book["original_publication_year"],
            "primary_cover_url": book["primary_cover_url"],
            "open_library_id": book["open_library_id"],
            "google_books_id": book["google_books_id"],
            "series_id": series_id,
            "series_position": (
                book["series_data"].get("position") if book.get("series_data") else None
            ),
            "formats": book["formats"],
            "cover_history": book["cover_history"],
            "isbn": book.get("isbn", []),
            "publisher": book.get("publisher"),
            "number_of_pages": book.get("number_of_pages"),
            "external_ids": book.get("external_ids", {}),
        }

        insert_data.append(book_entry)
        upsert_data.append(book_entry)

    stmt = postgresql_insert(app.models.book.Book).values(insert_data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["language", "slug"],
        set_={
            "description": stmt.excluded.description,
            "open_library_id": stmt.excluded.open_library_id,
            "google_books_id": stmt.excluded.google_books_id,
            "isbn": stmt.excluded.isbn,
            "publisher": stmt.excluded.publisher,
            "number_of_pages": stmt.excluded.number_of_pages,
            "external_ids": stmt.excluded.external_ids,
        },
    )

    await session.execute(stmt)

    book_slugs = [book["slug"] for book in cleaned_books]
    query = sqlalchemy.select(app.models.book.Book).where(
        app.models.book.Book.slug.in_(book_slugs)
    )
    result = await session.execute(query)
    rows = result.scalars().all()

    book_id_map = {row.slug: row.book_id for row in rows}
    inserted_count = len(rows)
    updated_count = len(cleaned_books) - inserted_count

    return {
        "book_id_map": book_id_map,
        "inserted": inserted_count,
        "updated": updated_count,
    }


async def _bulk_insert_relationships(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    cleaned_books: List[Dict[str, Any]],
    dedup_cache: Dict[str, Any],
    book_id_map: Dict[str, int],
    author_id_map: Dict[str, int],
    genre_id_map: Dict[str, int],
) -> None:
    book_authors_data = []
    book_genres_data = []

    for book in cleaned_books:
        book_id = book_id_map.get(book["slug"])
        if not book_id:
            continue

        for author_data in book.get("authors", []):
            author_slug = app.utils.slugify(author_data.get("name", ""))
            author_id = author_id_map.get(author_slug)
            if author_id:
                book_authors_data.append({"book_id": book_id, "author_id": author_id})

        for genre_data in book.get("genres", []):
            genre_name = genre_data.get("name", "")
            if isinstance(genre_name, str):
                genre_name = genre_name.lower()
            genre_slug = app.utils.slugify(genre_name)
            genre_id = genre_id_map.get(genre_slug)
            if genre_id:
                book_genres_data.append({"book_id": book_id, "genre_id": genre_id})

    if book_authors_data:
        stmt = postgresql_insert(app.models.book_author.BookAuthor).values(
            book_authors_data
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["book_id", "author_id"])
        await session.execute(stmt)

    if book_genres_data:
        stmt = postgresql_insert(app.models.book_genre.BookGenre).values(
            book_genres_data
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["book_id", "genre_id"])
        await session.execute(stmt)


async def insert_books(books_data: List[Dict[str, Any]]) -> Dict[str, int]:
    session = await get_db_session()

    try:
        return await insert_books_batch(session, books_data, commit=True)
    except Exception as e:
        logger.error(f"Error in insert_books: {str(e)}")
        raise
    finally:
        await session.close()


async def process_single_book(
    session: sqlalchemy.ext.asyncio.AsyncSession, book_data: Dict[str, Any]
) -> None:
    result = await insert_books_batch(session, [book_data], commit=False)
    if result["failed"] > 0:
        raise ValueError(f"Failed to process book: {book_data.get('title')}")
