import pytest
from sqlalchemy import select, func

from app.models import Book, Author, Genre, BookAuthor, BookGenre


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_book(db_session):
    book = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        description="A science fiction novel",
        original_publication_year=1984,
        formats=["hardcover", "ebook"],
        cover_history=[{"year": 1984, "cover_url": "http://example.com/cover.jpg", "publisher": "Ace"}],
        primary_cover_url="http://example.com/cover.jpg",
        open_library_id="OL123W",
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    db_session.add(book)
    await db_session.flush()

    assert book.book_id is not None
    assert book.title == "Neuromancer"
    assert book.language == "en"
    assert len(book.formats) == 2
    assert len(book.cover_history) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_author(db_session):
    author = Author(
        name="William Gibson",
        slug="william-gibson",
        bio="Canadian-American science fiction writer",
        open_library_id="OL456A"
    )

    db_session.add(author)
    await db_session.flush()

    assert author.author_id is not None
    assert author.name == "William Gibson"
    assert author.slug == "william-gibson"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_genre(db_session):
    genre = Genre(
        name="Science Fiction",
        slug="science-fiction"
    )

    db_session.add(genre)
    await db_session.flush()

    assert genre.genre_id is not None
    assert genre.name == "Science Fiction"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_book_author_relationship(db_session):
    book = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    author = Author(
        name="William Gibson",
        slug="william-gibson"
    )

    db_session.add(book)
    db_session.add(author)
    await db_session.flush()

    book_author = BookAuthor(book_id=book.book_id, author_id=author.author_id)
    db_session.add(book_author)
    await db_session.flush()

    result = await db_session.execute(
        select(BookAuthor).where(BookAuthor.book_id == book.book_id)
    )
    relationship = result.scalar_one()

    assert relationship.book_id == book.book_id
    assert relationship.author_id == author.author_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_book_genre_relationship(db_session):
    book = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    genre = Genre(
        name="Science Fiction",
        slug="science-fiction"
    )

    db_session.add(book)
    db_session.add(genre)
    await db_session.flush()

    book_genre = BookGenre(book_id=book.book_id, genre_id=genre.genre_id)
    db_session.add(book_genre)
    await db_session.flush()

    result = await db_session.execute(
        select(BookGenre).where(BookGenre.book_id == book.book_id)
    )
    relationship = result.scalar_one()

    assert relationship.book_id == book.book_id
    assert relationship.genre_id == genre.genre_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_book_unique_language_slug(db_session):
    book1 = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    db_session.add(book1)
    await db_session.flush()

    book2 = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    db_session.add(book2)

    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_book_different_languages(db_session):
    book_en = Book(
        title="Neuromancer",
        language="en",
        slug="neuromancer",
        ts_vector=func.to_tsvector('english', "Neuromancer")
    )

    book_fr = Book(
        title="Neuromancien",
        language="fr",
        slug="neuromancien",
        ts_vector=func.to_tsvector('french', "Neuromancien")
    )

    db_session.add(book_en)
    db_session.add(book_fr)
    await db_session.flush()

    result = await db_session.execute(select(Book))
    books = result.scalars().all()

    assert len(books) == 2
    assert {book.language for book in books} == {"en", "fr"}
