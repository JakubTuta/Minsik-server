import datetime

import pytest
from app.models import Author, Book, BookAuthor, BookGenre, Genre, Series
from app.workers import data_cleaner
from sqlalchemy import func, select, text

OLD_DATE = datetime.datetime(2020, 1, 1)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_low_quality_book(commit_session, session_factory_for_testing):
    book = Book(
        title="Bad Book",
        language="en",
        work_id="ol-bad-book", slug="bad-book",
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
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
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
        work_id="ol-good-book", slug="good-book",
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
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
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
        work_id="ol-viewed-book", slug="viewed-book",
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
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
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
        work_id="ol-rated-book", slug="rated-book",
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
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_never_deletes_user_engaged_low_quality_book(
    commit_session, session_factory_for_testing
):
    book = Book(
        title="Bad But Shelved Book",
        language="en",
        work_id="ol-bad-but-shelved-book", slug="bad-but-shelved-book",
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.flush()
    await commit_session.execute(
        text(
            "INSERT INTO user_data.bookshelves (user_id, book_id) VALUES (1, :book_id)"
        ),
        {"book_id": book.book_id},
    )
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_quality_books(
        session_factory_for_testing,
        min_quality_score=3,
        engagement_threshold=10,
        min_publication_year=1450,
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_duplicate_books_remaps_user_data_to_winner(
    commit_session, session_factory_for_testing
):
    author = Author(name="Same Author", slug="same-author")
    commit_session.add(author)
    await commit_session.flush()

    winner = Book(
        title="Duplicate Title",
        language="en",
        work_id="ol-duplicate-title", slug="duplicate-title",
        view_count=10,
        formats=[],
    )
    loser = Book(
        title="Duplicate Title",
        language="en",
        work_id="ol-duplicate-title-2", slug="duplicate-title-2",
        view_count=0,
        formats=[],
    )
    commit_session.add_all([winner, loser])
    await commit_session.flush()

    commit_session.add_all(
        [
            BookAuthor(book_id=winner.book_id, author_id=author.author_id),
            BookAuthor(book_id=loser.book_id, author_id=author.author_id),
        ]
    )
    await commit_session.execute(
        text(
            "INSERT INTO user_data.bookshelves (user_id, book_id) VALUES (1, :book_id)"
        ),
        {"book_id": loser.book_id},
    )
    await commit_session.commit()

    stats = await data_cleaner.cleanup_duplicate_books(
        session_factory_for_testing, batch_size=100
    )
    assert stats["deleted"] == 1

    remaining_books = await commit_session.execute(select(Book.book_id))
    remaining_ids = {row[0] for row in remaining_books.fetchall()}
    assert remaining_ids == {winner.book_id}

    shelf_result = await commit_session.execute(
        text("SELECT book_id FROM user_data.bookshelves WHERE user_id = 1")
    )
    assert shelf_result.scalar_one() == winner.book_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_authors(commit_session, session_factory_for_testing):
    orphan = Author(name="Nobody", slug="nobody", created_at=OLD_DATE)
    commit_session.add(orphan)
    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        session_factory_for_testing,
        min_books=2,
        max_books=1000,
        batch_size=100,
        spare_enriched=True,
        junk_publisher_names=True,
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
            work_id=f"ol-book-{i}", slug=f"book-{i}",
            formats=[],
        )
        commit_session.add(book)
        await commit_session.flush()
        commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))

    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        session_factory_for_testing,
        min_books=2,
        max_books=1000,
        batch_size=100,
        spare_enriched=True,
        junk_publisher_names=True,
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_consolidate_series_unlinks_underrepresented_group(
    commit_session, session_factory_for_testing
):
    book = Book(
        title="Short Book",
        language="en",
        work_id="ol-short-book", slug="short-book",
        series_slug="short-series",
        series_name="Short Series",
        series_position=1,
        formats=[],
    )
    commit_session.add(book)
    await commit_session.commit()

    await data_cleaner.consolidate_series(
        session_factory_for_testing, min_books=2, max_books=100, batch_size=100
    )

    series_count = await commit_session.execute(
        select(func.count()).select_from(Series)
    )
    assert series_count.scalar_one() == 0

    remaining_book = await commit_session.execute(
        select(Book.series_id).where(Book.slug == "short-book")
    )
    assert remaining_book.scalar_one() is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_consolidate_series_creates_per_language_rows(
    commit_session, session_factory_for_testing
):
    for i in range(2):
        commit_session.add(
            Book(
                title=f"Harry Potter {i}",
                language="en",
                work_id=f"ol-harry-potter-{i}", slug=f"harry-potter-{i}",
                series_slug="harry-potter",
                series_name="Harry Potter",
                series_position=i + 1,
                formats=[],
            )
        )
    for i in range(2):
        commit_session.add(
            Book(
                title=f"Harry Potter FR {i}",
                language="fr",
                work_id=f"ol-harry-potter-fr-{i}", slug=f"harry-potter-fr-{i}",
                series_slug="harry-potter",
                series_name="Harry Potter",
                series_position=i + 1,
                formats=[],
            )
        )
    await commit_session.commit()

    stats = await data_cleaner.consolidate_series(
        session_factory_for_testing, min_books=2, max_books=100, batch_size=100
    )
    assert stats["rows_created"] == 2

    series_rows = await commit_session.execute(
        select(Series.language, Series.total_books).where(Series.slug == "harry-potter")
    )
    rows = {row[0]: row[1] for row in series_rows.fetchall()}
    assert rows == {"en": 2, "fr": 2}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_consolidate_series_keeps_qualifying_series(
    commit_session, session_factory_for_testing
):
    for i in range(3):
        commit_session.add(
            Book(
                title=f"Long Book {i}",
                language="en",
                work_id=f"ol-long-book-{i}", slug=f"long-book-{i}",
                series_slug="long-series",
                series_name="Long Series",
                series_position=i + 1,
                formats=[],
            )
        )
    await commit_session.commit()

    stats = await data_cleaner.consolidate_series(
        session_factory_for_testing, min_books=2, max_books=100, batch_size=100
    )
    assert stats["rows_created"] == 1
    assert stats["linked"] == 3

    series_count = await commit_session.execute(
        select(func.count()).select_from(Series)
    )
    assert series_count.scalar_one() == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_normalize_genres_merges_variant_into_canonical(
    commit_session, session_factory_for_testing
):
    canonical = Genre(name="science fiction", slug="science-fiction")
    variant = Genre(name="Sci-Fi", slug="sci-fi")
    commit_session.add_all([canonical, variant])
    await commit_session.flush()

    book1 = Book(title="Book A", language="en", work_id="ol-book-a", slug="book-a", formats=[])
    book2 = Book(title="Book B", language="en", work_id="ol-book-b", slug="book-b", formats=[])
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

    book = Book(title="Some Sci-Fi Book", language="en", work_id="ol-some-sci-fi-book", slug="some-sci-fi-book", formats=[])
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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_placeholder_title_book(
    commit_session, session_factory_for_testing
):
    author = Author(name="Real Author", slug="real-author-2")
    genre = Genre(name="Fiction", slug="fiction-2")
    commit_session.add_all([author, genre])
    await commit_session.flush()

    book = Book(
        title="Untitled",
        language="en",
        work_id="ol-untitled-book", slug="untitled-book",
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
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 0
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_removes_ol_condemned_book(
    commit_session, session_factory_for_testing
):
    author = Author(name="Real Author", slug="real-author-3")
    genre = Genre(name="Fiction", slug="fiction-3")
    commit_session.add_all([author, genre])
    await commit_session.flush()

    book = Book(
        title="Condemned Book",
        language="en",
        work_id="ol-condemned-book", slug="condemned-book",
        description="A real book with a proper description.",
        primary_cover_url="http://example.com/cover.jpg",
        original_publication_year=2020,
        formats=["hardcover"],
        ol_rating_count=25,
        ol_avg_rating=1.0,
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
        max_title_length=300,
        ol_min_rating_count=20,
        ol_min_avg_rating=1.5,
        batch_size=100,
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 0
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_authors_spares_enriched_borderline_author(
    commit_session, session_factory_for_testing
):
    author = Author(
        name="Borderline Author",
        slug="borderline-author",
        bio="A well-documented author with a rich biography.",
        created_at=OLD_DATE,
    )
    commit_session.add(author)
    await commit_session.flush()

    book = Book(title="Solo Book", language="en", work_id="ol-solo-book", slug="solo-book", formats=[])
    commit_session.add(book)
    await commit_session.flush()
    commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))
    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        session_factory_for_testing,
        min_books=2,
        max_books=1000,
        batch_size=100,
        spare_enriched=True,
        junk_publisher_names=True,
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_orphan_authors_removes_junk_publisher_name(
    commit_session, session_factory_for_testing
):
    author = Author(
        name="Random House Publishing", slug="random-house-publishing", created_at=OLD_DATE
    )
    commit_session.add(author)
    await commit_session.flush()

    for i in range(3):
        book = Book(
            title=f"Publisher Book {i}",
            language="en",
            work_id=f"ol-publisher-book-{i}", slug=f"publisher-book-{i}",
            formats=[],
        )
        commit_session.add(book)
        await commit_session.flush()
        commit_session.add(BookAuthor(book_id=book.book_id, author_id=author.author_id))

    await commit_session.commit()

    stats = await data_cleaner.cleanup_orphan_authors(
        session_factory_for_testing,
        min_books=2,
        max_books=1000,
        batch_size=100,
        spare_enriched=True,
        junk_publisher_names=True,
    )

    result = await commit_session.execute(select(func.count()).select_from(Author))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0
