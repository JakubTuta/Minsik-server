import logging
import typing
import sqlalchemy
import sqlalchemy.ext.asyncio
import app.config
import app.models.book
import app.models.author
import app.models.genre
import app.models.series
import app.models.book_author
import app.models.book_genre
import app.utils

logger = logging.getLogger(__name__)


async def get_db_session() -> sqlalchemy.ext.asyncio.AsyncSession:
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        app.config.settings.database_url,
        pool_size=app.config.settings.db_pool_size,
        max_overflow=app.config.settings.db_max_overflow,
        echo=False
    )

    async_session = sqlalchemy.ext.asyncio.async_sessionmaker(
        engine,
        class_=sqlalchemy.ext.asyncio.AsyncSession,
        expire_on_commit=False
    )

    return async_session()


async def insert_books(books_data: list[typing.Dict[str, typing.Any]]) -> typing.Dict[str, int]:
    session = await get_db_session()

    try:
        successful = 0
        failed = 0

        for book_data in books_data:
            try:
                await process_single_book(session, book_data)
                successful += 1
            except Exception as e:
                logger.error(f"Error inserting book '{book_data.get('title')}': {str(e)}")
                failed += 1

        await session.commit()

        return {"successful": successful, "failed": failed}

    except Exception as e:
        logger.error(f"Error in batch insert: {str(e)}")
        await session.rollback()
        raise
    finally:
        await session.close()


async def process_single_book(session: sqlalchemy.ext.asyncio.AsyncSession, book_data: typing.Dict[str, typing.Any]) -> None:
    title = book_data.get("title")
    language = book_data.get("language", "en")
    slug = app.utils.slugify(title)

    query = sqlalchemy.select(app.models.book.Book).where(
        app.models.book.Book.language == language,
        app.models.book.Book.slug == slug
    )
    result = await session.execute(query)
    existing_book = result.scalar_one_or_none()

    if existing_book:
        await update_existing_book(session, existing_book, book_data)
    else:
        await create_new_book(session, book_data)


async def create_new_book(session: sqlalchemy.ext.asyncio.AsyncSession, book_data: typing.Dict[str, typing.Any]) -> None:
    series_id = None
    series_position = None

    series_data = book_data.get("series")
    if series_data:
        series = await get_or_create_series(session, series_data)
        series_id = series.series_id
        series_position = series_data.get("position")

    new_book = app.models.book.Book(
        title=book_data.get("title"),
        language=book_data.get("language", "en"),
        slug=app.utils.slugify(book_data.get("title")),
        description=book_data.get("description"),
        original_publication_year=book_data.get("original_publication_year"),
        primary_cover_url=book_data.get("primary_cover_url"),
        open_library_id=book_data.get("open_library_id"),
        google_books_id=book_data.get("google_books_id"),
        series_id=series_id,
        series_position=series_position
    )

    session.add(new_book)
    await session.flush()

    for author_data in book_data.get("authors", []):
        author = await get_or_create_author(session, author_data)
        book_author = app.models.book_author.BookAuthor(
            book_id=new_book.book_id,
            author_id=author.author_id
        )
        session.add(book_author)

    for genre_data in book_data.get("genres", []):
        genre = await get_or_create_genre(session, genre_data)
        book_genre = app.models.book_genre.BookGenre(
            book_id=new_book.book_id,
            genre_id=genre.genre_id
        )
        session.add(book_genre)

    new_book.formats = book_data.get("formats", [])
    new_book.cover_history = book_data.get("cover_history", [])


async def update_existing_book(session: sqlalchemy.ext.asyncio.AsyncSession, book: app.models.book.Book, book_data: typing.Dict[str, typing.Any]) -> None:
    if not book.description and book_data.get("description"):
        book.description = book_data.get("description")

    if book_data.get("open_library_id"):
        book.open_library_id = book_data.get("open_library_id")

    if book_data.get("google_books_id"):
        book.google_books_id = book_data.get("google_books_id")

    series_data = book_data.get("series")
    if series_data and not book.series_id:
        series = await get_or_create_series(session, series_data)
        book.series_id = series.series_id
        book.series_position = series_data.get("position")

    existing_formats = book.formats or []
    for format_name in book_data.get("formats", []):
        if format_name not in existing_formats:
            existing_formats.append(format_name)
    book.formats = existing_formats

    existing_covers = book.cover_history or []
    for cover_data in book_data.get("cover_history", []):
        cover_entry = {
            "year": cover_data.get("year"),
            "cover_url": cover_data.get("cover_url"),
            "publisher": cover_data.get("publisher")
        }
        if cover_entry not in existing_covers:
            existing_covers.append(cover_entry)
    book.cover_history = existing_covers


async def get_or_create_author(session: sqlalchemy.ext.asyncio.AsyncSession, author_data: typing.Dict[str, typing.Any]) -> app.models.author.Author:
    name = author_data.get("name")
    slug = app.utils.slugify(name)

    query = sqlalchemy.select(app.models.author.Author).where(
        app.models.author.Author.slug == slug
    )
    result = await session.execute(query)
    author = result.scalar_one_or_none()

    if author:
        if not author.bio and author_data.get("bio"):
            author.bio = author_data.get("bio")
        if not author.birth_date and author_data.get("birth_date"):
            author.birth_date = author_data.get("birth_date")
        if not author.death_date and author_data.get("death_date"):
            author.death_date = author_data.get("death_date")
        if not author.photo_url and author_data.get("photo_url"):
            author.photo_url = author_data.get("photo_url")
        if author_data.get("open_library_id"):
            author.open_library_id = author_data.get("open_library_id")
        return author

    new_author = app.models.author.Author(
        name=name,
        slug=slug,
        bio=author_data.get("bio"),
        birth_date=author_data.get("birth_date"),
        death_date=author_data.get("death_date"),
        photo_url=author_data.get("photo_url"),
        open_library_id=author_data.get("open_library_id")
    )
    session.add(new_author)
    await session.flush()

    return new_author


async def get_or_create_genre(session: sqlalchemy.ext.asyncio.AsyncSession, genre_data: typing.Dict[str, typing.Any]) -> app.models.genre.Genre:
    name = genre_data.get("name")
    slug = app.utils.slugify(name)

    query = sqlalchemy.select(app.models.genre.Genre).where(
        app.models.genre.Genre.slug == slug
    )
    result = await session.execute(query)
    genre = result.scalar_one_or_none()

    if genre:
        return genre

    new_genre = app.models.genre.Genre(
        name=name,
        slug=slug
    )
    session.add(new_genre)
    await session.flush()

    return new_genre


async def get_or_create_series(session: sqlalchemy.ext.asyncio.AsyncSession, series_data: typing.Dict[str, typing.Any]) -> app.models.series.Series:
    name = series_data.get("name")
    slug = app.utils.slugify(name)

    query = sqlalchemy.select(app.models.series.Series).where(
        app.models.series.Series.slug == slug
    )
    result = await session.execute(query)
    series = result.scalar_one_or_none()

    if series:
        if not series.description and series_data.get("description"):
            series.description = series_data.get("description")
        return series

    new_series = app.models.series.Series(
        name=name,
        slug=slug,
        description=series_data.get("description")
    )
    session.add(new_series)
    await session.flush()

    return new_series
