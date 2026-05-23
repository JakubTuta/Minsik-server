import datetime

import pytest
from app.models import Author, Book, BookAuthor, BookGenre, Genre, Series
from app.workers import data_cleaner
from sqlalchemy import func, select

OLD_DATE = datetime.datetime(2020, 1, 1)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_low_quality_book(commit_session, session_factory_for_testing):
    book = Book(
        title="Bad Book",
        language="en",
        slug="bad-book",
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        session_factory_for_testing,
        min_quality_score=3,
        engagement_threshold=10,
        min_publication_year=1450,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 0
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_high_quality_book(commit_session, session_factory_for_testing):
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
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.flush()

    commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))
    commit_session.add(BookGenre(book_id=book.book_id, genre_id=genre.genre_id))
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        session_factory_for_testing,
        min_quality_score=3,
        engagement_threshold=10,
        min_publication_year=1450,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_book_with_views(commit_session, session_factory_for_testing):
    book = Book(
        title="Viewed Book",
        language="en",
        slug="viewed-book",
        view_count=5,
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        session_factory_for_testing,
        min_quality_score=3,
        engagement_threshold=10,
        min_publication_year=1450,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_book_with_high_ratings(commit_session, session_factory_for_testing):
    author = Author(name="Popular Author", slug="popular-author")
    genre = Genre(name="Thriller", slug="thriller")
    commit_session.add_all([author, genre])
    await commit_session.flush()

    book = Book(
        title="Rated Book",
        language="en",
        slug="rated-book",
        rating_count=20,
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.flush()

    commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))
    commit_session.add(BookGenre(book_id=book.book_id, genre_id=genre.genre_id))
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        session_factory_for_testing,
        min_quality_score=3,
        engagement_threshold=10,
        min_publication_year=1450,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_authors(commit_session, session_factory_for_testing):
    orphan = Author(name="Nobody", slug="nobody", created_at=OLD_DATE)
    commit_session.add(orphan)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        session_factory_for_testing, min_books=2, max_books=1000, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 0
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_author_with_books(commit_session, session_factory_for_testing):
    author = Author(name="Prolific Author", slug="prolific-author")
    commit_session.add(author)
    await commit_session.flush()

    for i in range(2):
        book = Book(
            title=f"Book {i}",
            language="en",
            slug=f"book-{i}",
            formats=[],
        )
        commit_session.add(book)
        await commit_session.flush()
        commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))

    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        session_factory_for_testing, min_books=2, max_books=1000, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_short_series_without_deleting_books(
    commit_session, session_factory_for_testing
):
    series = Series(name="Short Series", slug="short-series", created_at=OLD_DATE)
    commit_session.add(series)
    await commit_session.flush()

    book = Book(
        title="Short Book",
        language="en",
        slug="short-book",
        series_id=series.series_id,
        series_position=1,
        formats=[],
    )
    commit_session.add(book)
    await commit_session.commit()

    deleted = await data_cleaner.cleanup_underrepresented_series(
        session_factory_for_testing, min_books=2, max_books=100, batch_size=100
    )
    assert deleted == 1

    series_count = await commit_session.execute(
        select(func.count()).select_from(Series)
    )
    assert series_count.scalar_one() == 0

    remaining_book = await commit_session.execute(
        select(Book.series_id, Book.series_position).where(Book.slug == "short-book")
    )
    detached_series_id, detached_series_position = remaining_book.one()
    assert detached_series_id is None
    assert detached_series_position is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_empty_series(commit_session, session_factory_for_testing):
    empty_series = Series(name="Empty Series", slug="empty-series", created_at=OLD_DATE)
    commit_session.add(empty_series)
    await commit_session.commit()

    deleted = await data_cleaner.cleanup_underrepresented_series(
        session_factory_for_testing, min_books=2, max_books=100, batch_size=100
    )
    assert deleted == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_keeps_series_with_many_books(
    commit_session, session_factory_for_testing
):
    series = Series(name="Long Series", slug="long-series", created_at=OLD_DATE)
    commit_session.add(series)
    await commit_session.flush()

    for i in range(3):
        book = Book(
            title=f"Long Book {i}",
            language="en",
            slug=f"long-book-{i}",
            series_id=series.series_id,
            series_position=i + 1,
            formats=[],
        )
        commit_session.add(book)

    await commit_session.commit()

    deleted = await data_cleaner.cleanup_underrepresented_series(
        session_factory_for_testing, min_books=2, max_books=100, batch_size=100
    )
    assert deleted == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_normalize_genres_merges_variant_into_canonical(
    commit_session, session_factory_for_testing
):
    canonical = Genre(name="science fiction", slug="science-fiction")
    variant = Genre(name="Sci-Fi", slug="sci-fi")
    commit_session.add_all([canonical, variant])
    await commit_session.flush()

    book1 = Book(title="Book A", language="en", slug="book-a", formats=[])
    book2 = Book(title="Book B", language="en", slug="book-b", formats=[])
    commit_session.add_all([book1, book2])
    await commit_session.flush()

    commit_session.add(
        BookGenre(book_id=book1.book_id, genre_id=canonical.genre_id)
    )
    commit_session.add(
        BookGenre(book_id=book2.book_id, genre_id=variant.genre_id)
    )
    await commit_session.commit()

    merged = await data_cleaner.normalize_and_merge_genres(
        session_factory_for_testing, batch_size=100
    )

    await commit_session.reset()

    genre_count = await commit_session.execute(
        select(func.count()).select_from(Genre)
    )
    assert genre_count.scalar_one() == 1

    bk_genre_count = await commit_session.execute(
        select(func.count()).select_from(BookGenre)
    )
    assert bk_genre_count.scalar_one() == 2

    assert merged >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_normalize_genres_renames_variant_when_no_canonical_exists(
    commit_session, session_factory_for_testing
):
    variant = Genre(name="Sci-Fi", slug="sci-fi")
    commit_session.add(variant)
    await commit_session.flush()

    book = Book(title="Some Sci-Fi Book", language="en", slug="some-sci-fi-book", formats=[])
    commit_session.add(book)
    await commit_session.flush()

    commit_session.add(BookGenre(book_id=book.book_id, genre_id=variant.genre_id))
    await commit_session.commit()

    merged = await data_cleaner.normalize_and_merge_genres(
        session_factory_for_testing, batch_size=100
    )

    await commit_session.reset()

    result = await commit_session.execute(
        select(Genre).where(Genre.slug == "science-fiction")
    )
    assert result.scalar_one_or_none() is not None
    assert merged >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_normalize_genres_skips_already_canonical(
    commit_session, session_factory_for_testing
):
    genre = Genre(name="science fiction", slug="science-fiction")
    commit_session.add(genre)
    await commit_session.commit()

    merged = await data_cleaner.normalize_and_merge_genres(
        session_factory_for_testing, batch_size=100
    )

    await commit_session.reset()

    count = await commit_session.execute(
        select(func.count()).select_from(Genre)
    )
    assert count.scalar_one() == 1
    assert merged == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_genres(commit_session, session_factory_for_testing):
    genre = Genre(name="Dead Genre", slug="dead-genre", created_at=OLD_DATE)
    commit_session.add(genre)
    await commit_session.commit()

    deleted = await data_cleaner.cleanup_orphan_genres(
        session_factory_for_testing, batch_size=100
    )
    assert deleted == 1
