import datetime

import pytest
from app.models import Author, Book, BookAuthor, Genre, Series
from app.workers import data_cleaner
from sqlalchemy import func, select, text

OLD_DATE = datetime.datetime(2020, 1, 1)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_low_engagement_books_removes_unnoticed_book(
    commit_session, session_factory_for_testing
):
    ignored = Book(
        title="Ignored Book",
        language="en",
        work_id="ol-ignored-book",
        slug="ignored-book",
        ol_rating_count=2,
        ol_want_to_read_count=3,
        formats=[],
        created_at=OLD_DATE,
    )
    noticed = Book(
        title="Noticed Book",
        language="en",
        work_id="ol-noticed-book",
        slug="noticed-book",
        ol_rating_count=4,
        ol_already_read_count=6,
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add_all([ignored, noticed])
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_engagement_books(
        session_factory_for_testing, min_ol_engagement=10, batch_size=100
    )

    remaining = await commit_session.execute(select(Book.slug))
    assert {row[0] for row in remaining.fetchall()} == {"noticed-book"}
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_low_engagement_books_keeps_user_engaged_book(
    commit_session, session_factory_for_testing
):
    book = Book(
        title="Shelved Obscure Book",
        language="en",
        work_id="ol-shelved-obscure",
        slug="shelved-obscure",
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add(book)
    await commit_session.flush()
    await commit_session.execute(
        text("INSERT INTO user_data.bookshelves (user_id, book_id) VALUES (1, :book_id)"),
        {"book_id": book.book_id},
    )
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_engagement_books(
        session_factory_for_testing, min_ol_engagement=10, batch_size=100
    )

    result = await commit_session.execute(select(func.count()).select_from(Book))
    assert result.scalar_one() == 1
    assert stats["deleted"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_multi_author_books(commit_session, session_factory_for_testing):
    crowded = Book(
        title="Crowded Entry",
        language="en",
        work_id="ol-crowded",
        slug="crowded",
        formats=[],
        created_at=OLD_DATE,
    )
    normal = Book(
        title="Normal Book",
        language="en",
        work_id="ol-normal",
        slug="normal",
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add_all([crowded, normal])
    await commit_session.flush()

    for i in range(10):
        author = Author(name=f"Contributor {i}", slug=f"contributor-{i}")
        commit_session.add(author)
        await commit_session.flush()
        commit_session.add(
            BookAuthor(book_id=crowded.book_id, author_id=author.author_id)
        )
        if i == 0:
            commit_session.add(
                BookAuthor(book_id=normal.book_id, author_id=author.author_id)
            )
    await commit_session.commit()

    stats = await data_cleaner.cleanup_multi_author_books(
        session_factory_for_testing, max_authors=10, batch_size=100
    )

    remaining = await commit_session.execute(select(Book.slug))
    assert {row[0] for row in remaining.fetchall()} == {"normal"}
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_collection_books(commit_session, session_factory_for_testing):
    titles = {
        "boxed-set": "Wheel of Time Boxed Set",
        "complete-works": "The Complete Works of Shakespeare",
        "books-1-3": "Dune Books 1-3",
        "trilogy-tail": "The Forestwife Trilogy",
        "single": "Dune",
        "series-descriptor": "Daughter of the Blood (The Black Jewels Trilogy, Book 1)",
        "series-in-title": "Star Wars - Thrawn Trilogy - Heir to the Empire",
        "provenance": "The Old Testament manuscripts in the Freer collection",
    }
    for slug, title in titles.items():
        commit_session.add(
            Book(
                title=title,
                language="en",
                work_id=f"ol-{slug}",
                slug=slug,
                formats=[],
                created_at=OLD_DATE,
            )
        )
    await commit_session.commit()

    stats = await data_cleaner.cleanup_collection_books(
        session_factory_for_testing, batch_size=100
    )

    remaining = await commit_session.execute(select(Book.slug))
    assert {row[0] for row in remaining.fetchall()} == {
        "single",
        "series-descriptor",
        "series-in-title",
        "provenance",
    }
    assert stats["deleted"] == 4


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_collection_authors(commit_session, session_factory_for_testing):
    names = {
        "various-authors": "Various Authors",
        "anonymous": "Anonymous",
        "smith-john-doe-jane": "Smith, John; Doe, Jane",
        "arkady-and-boris-strugatsky": "Arkady and Boris Strugatsky",
        "ursula-k-le-guin": "Ursula K. Le Guin",
    }
    for slug, name in names.items():
        commit_session.add(Author(name=name, slug=slug, created_at=OLD_DATE))
    await commit_session.commit()

    stats = await data_cleaner.cleanup_collection_authors(
        session_factory_for_testing, batch_size=100
    )

    remaining = await commit_session.execute(select(Author.slug))
    assert {row[0] for row in remaining.fetchall()} == {
        "ursula-k-le-guin",
        "arkady-and-boris-strugatsky",
    }
    assert stats["deleted"] == 3


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_low_engagement_authors(
    commit_session, session_factory_for_testing
):
    ignored = Author(name="Ignored Writer", slug="ignored-writer", created_at=OLD_DATE)
    noticed = Author(name="Noticed Writer", slug="noticed-writer", created_at=OLD_DATE)
    commit_session.add_all([ignored, noticed])
    await commit_session.flush()

    ignored_book = Book(
        title="Ignored Writer Book",
        language="en",
        work_id="ol-ignored-writer-book",
        slug="ignored-writer-book",
        ol_rating_count=1,
        formats=[],
        created_at=OLD_DATE,
    )
    noticed_book = Book(
        title="Noticed Writer Book",
        language="en",
        work_id="ol-noticed-writer-book",
        slug="noticed-writer-book",
        ol_already_read_count=50,
        formats=[],
        created_at=OLD_DATE,
    )
    commit_session.add_all([ignored_book, noticed_book])
    await commit_session.flush()
    commit_session.add_all(
        [
            BookAuthor(book_id=ignored_book.book_id, author_id=ignored.author_id),
            BookAuthor(book_id=noticed_book.book_id, author_id=noticed.author_id),
        ]
    )
    await commit_session.commit()

    stats = await data_cleaner.cleanup_low_engagement_authors(
        session_factory_for_testing, min_ol_engagement=10, batch_size=100
    )

    remaining_authors = await commit_session.execute(select(Author.slug))
    assert {row[0] for row in remaining_authors.fetchall()} == {"noticed-writer"}
    assert stats["deleted"] == 1

    remaining_books = await commit_session.execute(select(Book.slug))
    assert {row[0] for row in remaining_books.fetchall()} == {"noticed-writer-book"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_duplicate_books_by_work_id(
    commit_session, session_factory_for_testing
):
    winner = Book(
        title="Same Work Preferred Edition",
        language="en",
        work_id="ol-same-work",
        slug="same-work-a",
        ol_rating_count=30,
        formats=[],
    )
    loser = Book(
        title="Same Work Other Edition",
        language="en",
        work_id="ol-same-work",
        slug="same-work-b",
        formats=[],
    )
    commit_session.add_all([winner, loser])
    await commit_session.commit()

    stats = await data_cleaner.cleanup_duplicate_books(
        session_factory_for_testing, batch_size=100
    )

    remaining = await commit_session.execute(select(Book.slug))
    assert {row[0] for row in remaining.fetchall()} == {"same-work-a"}
    assert stats["deleted"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_junk_genres(commit_session, session_factory_for_testing):
    commit_session.add_all(
        [
            Genre(name="accessible book", slug="accessible-book"),
            Genre(name="protected daisy", slug="protected-daisy"),
            Genre(name="fantasy", slug="fantasy"),
        ]
    )
    await commit_session.commit()

    deleted = await data_cleaner.cleanup_junk_genres(
        session_factory_for_testing, batch_size=100
    )

    remaining = await commit_session.execute(select(Genre.slug))
    assert {row[0] for row in remaining.fetchall()} == {"fantasy"}
    assert deleted == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_consolidate_series_skips_low_engagement_group(
    commit_session, session_factory_for_testing
):
    for i in range(2):
        commit_session.add(
            Book(
                title=f"Obscure Series Book {i}",
                language="en",
                work_id=f"ol-obscure-series-{i}",
                slug=f"obscure-series-{i}",
                series_slug="obscure-series",
                series_name="Obscure Series",
                series_position=i + 1,
                formats=[],
            )
        )
    await commit_session.commit()

    stats = await data_cleaner.consolidate_series(
        session_factory_for_testing,
        min_books=2,
        max_books=100,
        batch_size=100,
        min_ol_engagement=10,
    )

    assert stats["rows_created"] == 0
    series_count = await commit_session.execute(select(func.count()).select_from(Series))
    assert series_count.scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_consolidate_series_clears_collection_descriptors(
    commit_session, session_factory_for_testing
):
    commit_session.add(
        Book(
            title="Bundled Story",
            language="en",
            work_id="ol-bundled-story",
            slug="bundled-story",
            series_slug="the-complete-collection",
            series_name="The Complete Collection",
            series_position=1,
            formats=[],
        )
    )
    await commit_session.commit()

    stats = await data_cleaner.consolidate_series(
        session_factory_for_testing, min_books=1, max_books=100, batch_size=100
    )

    assert stats["descriptors_cleared"] == 1
    result = await commit_session.execute(
        select(Book.series_slug, Book.series_name).where(Book.slug == "bundled-story")
    )
    assert result.one() == (None, None)
