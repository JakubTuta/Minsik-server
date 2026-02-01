import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select, func

from app.models import Book, Author, Genre
from app.workers.ingestion_worker import (
    _process_single_book,
    _create_new_book,
    _update_existing_book,
    _get_or_create_author,
    _get_or_create_genre
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_new_book(db_session, sample_book_data):
    await _create_new_book(db_session, sample_book_data)

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one_or_none()

    assert book is not None
    assert book.title == "Neuromancer"
    assert book.language == "en"
    assert len(book.formats) == 2
    assert "hardcover" in book.formats
    assert "ebook" in book.formats


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_existing_book(db_session):
    existing_book = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        formats=["hardcover"],
        cover_history=[
            {"year": 1984, "cover_url": "http://example.com/old.jpg", "publisher": "Old Publisher"}
        ],
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    db_session.add(existing_book)
    await db_session.flush()

    new_book_data = {
        "title": "Neuromancer",
        "language": "en",
        "slug": "neuromancer",
        "formats": ["ebook"],
        "cover_history": [
            {"year": 1985, "cover_url": "http://example.com/new.jpg", "publisher": "New Publisher"}
        ],
        "description": "Updated description",
        "open_library_id": "OL123W"
    }

    await _update_existing_book(db_session, existing_book, new_book_data)
    await db_session.flush()

    assert len(existing_book.formats) == 2
    assert "hardcover" in existing_book.formats
    assert "ebook" in existing_book.formats
    assert len(existing_book.cover_history) == 2
    assert existing_book.description == "Updated description"
    assert existing_book.open_library_id == "OL123W"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_or_create_author_new(db_session):
    author_data = {
        "name": "William Gibson",
        "slug": "william-gibson",
        "bio": "Canadian-American science fiction writer",
        "open_library_id": "OL456A"
    }

    author_id = await _get_or_create_author(db_session, author_data)

    assert author_id is not None

    result = await db_session.execute(
        select(Author).where(Author.author_id == author_id)
    )
    author = result.scalar_one()

    assert author.name == "William Gibson"
    assert author.slug == "william-gibson"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_or_create_author_existing(db_session):
    existing_author = Author(
        name="William Gibson",
        slug="william-gibson"
    )

    db_session.add(existing_author)
    await db_session.flush()

    author_data = {
        "name": "William Gibson",
        "slug": "william-gibson",
        "bio": "Updated bio"
    }

    author_id = await _get_or_create_author(db_session, author_data)

    assert author_id == existing_author.author_id

    result = await db_session.execute(select(Author))
    authors = result.scalars().all()

    assert len(authors) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_or_create_genre_new(db_session):
    genre_data = {
        "name": "Science Fiction",
        "slug": "science-fiction"
    }

    genre_id = await _get_or_create_genre(db_session, genre_data)

    assert genre_id is not None

    result = await db_session.execute(
        select(Genre).where(Genre.genre_id == genre_id)
    )
    genre = result.scalar_one()

    assert genre.name == "Science Fiction"
    assert genre.slug == "science-fiction"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_or_create_genre_existing(db_session):
    existing_genre = Genre(
        name="Science Fiction",
        slug="science-fiction"
    )

    db_session.add(existing_genre)
    await db_session.flush()

    genre_data = {
        "name": "Science Fiction",
        "slug": "science-fiction"
    }

    genre_id = await _get_or_create_genre(db_session, genre_data)

    assert genre_id == existing_genre.genre_id

    result = await db_session.execute(select(Genre))
    genres = result.scalars().all()

    assert len(genres) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_single_book_new(db_session, sample_book_data):
    await _process_single_book(db_session, sample_book_data)

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.title == "Neuromancer"

    result = await db_session.execute(select(Author))
    authors = result.scalars().all()
    assert len(authors) == 1

    result = await db_session.execute(select(Genre))
    genres = result.scalars().all()
    assert len(genres) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_single_book_duplicate(db_session, sample_book_data):
    await _process_single_book(db_session, sample_book_data)

    updated_data = sample_book_data.copy()
    updated_data["formats"] = ["audiobook"]
    updated_data["cover_history"] = [
        {"year": 1985, "cover_url": "http://example.com/new.jpg", "publisher": "New Publisher"}
    ]

    await _process_single_book(db_session, updated_data)

    result = await db_session.execute(select(Book))
    books = result.scalars().all()

    assert len(books) == 1
    assert "audiobook" in books[0].formats
    assert len(books[0].cover_history) == 2
