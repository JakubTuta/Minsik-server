from unittest.mock import AsyncMock, patch

import pytest
from app.models import Author, Book, Genre
from app.services.book_service import insert_books_batch, process_single_book
from sqlalchemy import func, select


@pytest.mark.asyncio
@pytest.mark.integration
async def test_insert_single_book(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

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
async def test_update_existing_book(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    updated_data = sample_book_data.copy()
    updated_data["description"] = "Updated description"
    updated_data["open_library_id"] = "OL123W"

    await process_single_book(db_session, updated_data)
    await db_session.flush()

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.description == "Updated description"
    assert book.open_library_id == "OL123W"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_insert_book_creates_author(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    result = await db_session.execute(select(Author))
    authors = result.scalars().all()

    assert len(authors) == 1
    assert authors[0].name == "William Gibson"
    assert authors[0].slug == "william-gibson"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_insert_book_reuses_existing_author(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    second_book_data = sample_book_data.copy()
    second_book_data["title"] = "Count Zero"

    await process_single_book(db_session, second_book_data)

    result = await db_session.execute(select(Author))
    authors = result.scalars().all()

    assert len(authors) == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_insert_book_creates_genres(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    result = await db_session.execute(select(Genre))
    genres = result.scalars().all()

    assert len(genres) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_insert_book_reuses_existing_genre(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    second_book_data = sample_book_data.copy()
    second_book_data["title"] = "Count Zero"

    await process_single_book(db_session, second_book_data)

    result = await db_session.execute(select(Genre))
    genres = result.scalars().all()

    assert len(genres) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_process_single_book_new(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

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
    await process_single_book(db_session, sample_book_data)

    updated_data = sample_book_data.copy()
    updated_data["formats"] = ["audiobook"]
    updated_data["cover_history"] = [
        {
            "year": 1985,
            "cover_url": "http://example.com/new.jpg",
            "publisher": "New Publisher",
        }
    ]

    await process_single_book(db_session, updated_data)

    result = await db_session.execute(select(Book))
    books = result.scalars().all()

    assert len(books) == 1
    assert "audiobook" in books[0].formats
    assert len(books[0].cover_history) == 2
