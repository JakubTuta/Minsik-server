from unittest.mock import AsyncMock, MagicMock, patch

import app.services.author_service as author_service
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_author():
    author = MagicMock()
    author.author_id = 1
    author.name = "J.K. Rowling"
    author.slug = "jk-rowling"
    author.bio = "British author"
    author.birth_date = None
    author.death_date = None
    author.photo_url = "http://example.com/photo.jpg"
    author.view_count = 1000
    author.last_viewed_at = None
    author.open_library_id = "OL123456A"
    author.created_at = None
    author.updated_at = None
    return author


@pytest.fixture
def mock_book():
    book = MagicMock()
    book.book_id = 1
    book.title = "Harry Potter"
    book.slug = "harry-potter"
    book.description = "A magical book"
    book.original_publication_year = 1997
    book.primary_cover_url = "http://example.com/cover.jpg"
    book.rating_count = 500
    book.avg_rating = 4.5
    book.view_count = 2000
    book.created_at = None

    genre = MagicMock()
    genre.genre_id = 1
    genre.name = "Fantasy"
    genre.slug = "fantasy"
    book.genres = [genre]

    return book


class TestAuthorService:
    @pytest.mark.asyncio
    async def test_get_author_by_slug_cache_hit(self, mock_session):
        cached_author = {
            "author_id": 1,
            "name": "J.K. Rowling",
            "slug": "jk-rowling",
            "books_count": 7,
        }

        with patch("app.cache.get_cached", return_value=cached_author), patch(
            "app.cache.increment_view_count"
        ) as mock_track:

            result = await author_service.get_author_by_slug(mock_session, "jk-rowling")

            assert result == cached_author
            mock_track.assert_called_once_with("author", 1)

    @pytest.mark.asyncio
    async def test_get_author_by_slug_cache_miss(self, mock_session, mock_author):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_author

        mock_categories_result = MagicMock()
        mock_categories_result.fetchall.return_value = [("Fantasy",), ("Fiction",)]

        mock_aggregates_row = MagicMock()
        mock_aggregates_row.books_count = 7
        mock_aggregates_row.weighted_rating_sum = 2250.0
        mock_aggregates_row.total_ratings = 500
        mock_aggregates_row.total_views = 2000
        mock_aggregates_result = MagicMock()
        mock_aggregates_result.first.return_value = mock_aggregates_row

        mock_session.execute.side_effect = [
            mock_result,
            mock_categories_result,
            mock_aggregates_result,
        ]

        with patch("app.cache.get_cached", return_value=None), patch(
            "app.cache.set_cached"
        ) as mock_set_cache, patch("app.cache.increment_view_count"):

            result = await author_service.get_author_by_slug(mock_session, "jk-rowling")

            assert result is not None
            assert result["name"] == "J.K. Rowling"
            assert result["slug"] == "jk-rowling"
            assert result["books_count"] == 7
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_author_by_slug_not_found(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("app.cache.get_cached", return_value=None):
            result = await author_service.get_author_by_slug(
                mock_session, "nonexistent"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_author_books_cache_hit(self, mock_session):
        cached_data = {"books": [{"book_id": 1, "title": "Book 1"}], "total": 7}

        with patch("app.cache.get_cached", return_value=cached_data):
            books, total = await author_service.get_author_books(
                mock_session, "jk-rowling", 10, 0
            )

            assert books == cached_data["books"]
            assert total == 7

    @pytest.mark.asyncio
    async def test_get_author_books_cache_miss(
        self, mock_session, mock_author, mock_book
    ):
        mock_author_result = MagicMock()
        mock_author_result.scalar_one_or_none.return_value = mock_author

        mock_books_result = MagicMock()
        mock_books_result.scalars.return_value.all.return_value = [mock_book]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 7

        mock_session.execute.side_effect = [
            mock_author_result,
            mock_books_result,
            mock_count_result,
        ]

        with patch("app.cache.get_cached", return_value=None), patch(
            "app.cache.set_cached"
        ) as mock_set_cache:

            books, total = await author_service.get_author_books(
                mock_session, "jk-rowling", 10, 0
            )

            assert len(books) == 1
            assert books[0]["title"] == "Harry Potter"
            assert total == 7
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_author_books_author_not_found(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch("app.cache.get_cached", return_value=None):
            books, total = await author_service.get_author_books(
                mock_session, "nonexistent", 10, 0
            )

            assert books == []
            assert total == 0

    def test_author_to_dict(self, mock_author):
        book_categories = ["Fantasy", "Fiction"]
        books_aggregates = {
            "books_count": 7,
            "avg_rating": 4.5,
            "total_ratings": 500,
            "total_views": 2000,
        }
        result = author_service._author_to_dict(
            mock_author, book_categories, books_aggregates
        )

        assert result["author_id"] == 1
        assert result["name"] == "J.K. Rowling"
        assert result["slug"] == "jk-rowling"
        assert result["bio"] == "British author"
        assert result["books_count"] == 7
        assert result["view_count"] == 1000

    def test_book_summary_to_dict(self, mock_book):
        result = author_service._book_summary_to_dict(mock_book)

        assert result["book_id"] == 1
        assert result["title"] == "Harry Potter"
        assert result["slug"] == "harry-potter"
        assert result["description"] == "A magical book"
        assert result["avg_rating"] == "4.5"
        assert len(result["genres"]) == 1
        assert result["genres"][0]["name"] == "Fantasy"

    @pytest.mark.asyncio
    async def test_flush_view_counts_to_db(self, mock_session):
        pending_counts = {
            1: {"count": 5, "last_viewed": 1234567890},
            2: {"count": 3, "last_viewed": 1234567891},
        }

        with patch(
            "app.cache.get_pending_view_counts", return_value=pending_counts
        ), patch("app.cache.clear_view_counts") as mock_clear:

            await author_service.flush_view_counts_to_db(mock_session)

            assert mock_session.execute.call_count == 2
            mock_session.commit.assert_called_once()
            mock_clear.assert_called_once_with("author", [1, 2])

    @pytest.mark.asyncio
    async def test_flush_view_counts_to_db_empty(self, mock_session):
        with patch("app.cache.get_pending_view_counts", return_value=None):
            await author_service.flush_view_counts_to_db(mock_session)

            mock_session.execute.assert_not_called()
            mock_session.commit.assert_not_called()
