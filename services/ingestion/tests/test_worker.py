import pytest
from app.models import Author, Book, Genre
from app.services.book_service import process_single_book
from sqlalchemy import select


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
    updated_data["description"] = (
        "A much longer updated description with substantially more detail than before."
    )
    updated_data["open_library_id"] = "OL123W"

    await process_single_book(db_session, updated_data)
    await db_session.flush()

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.description == updated_data["description"]
    assert book.open_library_id == "OL123W"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reingest_does_not_shorten_description(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    shorter_data = sample_book_data.copy()
    shorter_data["description"] = "Short."

    await process_single_book(db_session, shorter_data)
    await db_session.flush()

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.description == sample_book_data["description"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reingest_preserves_existing_publisher_and_isbn(db_session, sample_book_data):
    first_data = sample_book_data.copy()
    first_data["publisher"] = "Ace Books"
    first_data["isbn"] = ["9780441569595"]
    await process_single_book(db_session, first_data)

    second_data = sample_book_data.copy()
    second_data["publisher"] = "Different Publisher"
    second_data["isbn"] = ["0000000000000"]
    await process_single_book(db_session, second_data)
    await db_session.flush()

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.publisher == "Ace Books"
    assert book.isbn == ["9780441569595"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reingest_fills_null_fields(db_session, sample_book_data):
    first_data = sample_book_data.copy()
    first_data["publisher"] = None
    first_data["number_of_pages"] = None
    await process_single_book(db_session, first_data)

    second_data = sample_book_data.copy()
    second_data["publisher"] = "Ace Books"
    second_data["number_of_pages"] = 271
    await process_single_book(db_session, second_data)
    await db_session.flush()

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.publisher == "Ace Books"
    assert book.number_of_pages == 271


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
    first_data = sample_book_data.copy()
    first_data["formats"] = []
    await process_single_book(db_session, first_data)

    updated_data = sample_book_data.copy()
    updated_data["formats"] = ["audiobook"]

    await process_single_book(db_session, updated_data)

    result = await db_session.execute(select(Book))
    books = result.scalars().all()

    assert len(books) == 1
    assert "audiobook" in books[0].formats


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reingest_does_not_replace_existing_formats(db_session, sample_book_data):
    await process_single_book(db_session, sample_book_data)

    updated_data = sample_book_data.copy()
    updated_data["formats"] = ["audiobook"]
    await process_single_book(db_session, updated_data)

    result = await db_session.execute(
        select(Book).where(Book.slug == "neuromancer", Book.language == "en")
    )
    book = result.scalar_one()

    assert book.formats == sample_book_data["formats"]
