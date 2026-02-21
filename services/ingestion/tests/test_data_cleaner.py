import datetime

import pytest
from app.models import Author, Book, BookAuthor, BookGenre, Genre, Series
from app.workers import data_cleaner
from sqlalchemy import func, select

OLD_DATE = datetime.datetime(2020, 1, 1)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_low_quality_book(commit_session):
    book = Book(
        title="Bad Book",
        language="en",
        slug="bad-book",
        formats=[],
        cover_history=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        commit_session, min_quality_score=3, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 0
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_high_quality_book(commit_session):
    author = Author(name="Real Author", slug="real-author")
    genre = Genre(name="Fiction", slug="fiction")
    commit_session.add_all([author, genre])
    await commit_session.flush()

    book = Book(
        title="Good Book",
        language="en",
        slug="good-book",
        description="A real book with a proper description.",
        primary_cover_url="http://example.com/cover.jpg",
        original_publication_year=2020,
        formats=["hardcover"],
        cover_history=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.flush()

    commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))
    commit_session.add(BookGenre(book_id=book.book_id, genre_id=genre.genre_id))
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        commit_session, min_quality_score=3, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_book_with_views(commit_session):
    book = Book(
        title="Viewed Book",
        language="en",
        slug="viewed-book",
        view_count=5,
        formats=[],
        cover_history=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        commit_session, min_quality_score=3, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_book_with_ratings(commit_session):
    book = Book(
        title="Rated Book",
        language="en",
        slug="rated-book",
        rating_count=1,
        formats=[],
        cover_history=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        commit_session, min_quality_score=3, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_authors(commit_session):
    orphan = Author(name="Nobody", slug="nobody", created_at=OLD_DATE)
    commit_session.add(orphan)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        commit_session, min_books=2, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 0
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_author_with_books(commit_session):
    author = Author(name="Prolific Author", slug="prolific-author")
    commit_session.add(author)
    await commit_session.flush()

    for i in range(2):
        book = Book(
            title=f"Book {i}",
            language="en",
            slug=f"book-{i}",
            formats=[],
            cover_history=[],
        )
        commit_session.add(book)
        await commit_session.flush()
        commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))

    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        commit_session, min_books=2, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_viewed_author(commit_session):
    author = Author(name="Famous Author", slug="famous-author", view_count=10)
    commit_session.add(author)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        commit_session, min_books=2, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_series(commit_session):
    series = Series(name="Dead Series", slug="dead-series", created_at=OLD_DATE)
    commit_session.add(series)
    await commit_session.commit()

    deleted = await data_cleaner.cleanup_orphan_series(commit_session, batch_size=100)
    assert deleted == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_genres(commit_session):
    genre = Genre(name="Dead Genre", slug="dead-genre", created_at=OLD_DATE)
    commit_session.add(genre)
    await commit_session.commit()

    deleted = await data_cleaner.cleanup_orphan_genres(commit_session, batch_size=100)
    assert deleted == 1
