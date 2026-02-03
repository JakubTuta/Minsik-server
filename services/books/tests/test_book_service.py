import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import app.services.book_service as book_service


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_book():
    book = MagicMock()
    book.book_id = 1
    book.title = "Test Book"
    book.slug = "test-book"
    book.description = "A test book description"
    book.language = "en"
    book.original_publication_year = 2020
    book.formats = ["paperback", "ebook"]
    book.primary_cover_url = "http://example.com/cover.jpg"
    book.cover_history = []
    book.rating_count = 100
    book.avg_rating = 4.5
    book.view_count = 500
    book.last_viewed_at = None
    book.open_library_id = "OL123456W"
    book.google_books_id = "GB123456"
    book.created_at = None
    book.updated_at = None
    book.series = None
    book.series_position = None
    book.authors = []
    book.genres = []
    return book


@pytest.fixture
def mock_book_with_series():
    book = MagicMock()
    book.book_id = 1
    book.title = "Harry Potter and the Philosopher's Stone"
    book.slug = "harry-potter-philosophers-stone"
    book.series_position = 1.0

    series = MagicMock()
    series.series_id = 1
    series.name = "Harry Potter"
    series.slug = "harry-potter"
    series.total_books = 7

    book.series = series
    book.authors = []
    book.genres = []
    return book


class TestBookService:
    @pytest.mark.asyncio
    async def test_get_book_by_slug_cache_hit(self, mock_session):
        cached_book = {
            "book_id": 1,
            "title": "Test Book",
            "slug": "test-book"
        }

        with patch('app.cache.get_cached', return_value=cached_book), \
             patch('app.cache.increment_view_count') as mock_track:

            result = await book_service.get_book_by_slug(mock_session, "test-book")

            assert result == cached_book
            mock_track.assert_called_once_with("book", 1)

    @pytest.mark.asyncio
    async def test_get_book_by_slug_cache_miss(self, mock_session, mock_book):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_book
        mock_session.execute.return_value = mock_result

        with patch('app.cache.get_cached', return_value=None), \
             patch('app.cache.set_cached') as mock_set_cache, \
             patch('app.cache.increment_view_count'):

            result = await book_service.get_book_by_slug(mock_session, "test-book")

            assert result is not None
            assert result["title"] == "Test Book"
            assert result["slug"] == "test-book"
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_book_by_slug_not_found(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch('app.cache.get_cached', return_value=None):
            result = await book_service.get_book_by_slug(mock_session, "nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_book_with_series(self, mock_session, mock_book_with_series):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_book_with_series
        mock_session.execute.return_value = mock_result

        with patch('app.cache.get_cached', return_value=None), \
             patch('app.cache.set_cached'), \
             patch('app.cache.increment_view_count'):

            result = await book_service.get_book_by_slug(mock_session, "harry-potter-philosophers-stone")

            assert result is not None
            assert result["series"] is not None
            assert result["series"]["name"] == "Harry Potter"
            assert result["series_position"] == "1.0"

    def test_book_to_dict_without_series(self, mock_book):
        result = book_service._book_to_dict(mock_book)

        assert result["book_id"] == 1
        assert result["title"] == "Test Book"
        assert result["slug"] == "test-book"
        assert result["series"] is None
        assert result["series_position"] == ""

    def test_book_to_dict_with_series(self, mock_book_with_series):
        result = book_service._book_to_dict(mock_book_with_series)

        assert result["series"] is not None
        assert result["series"]["name"] == "Harry Potter"
        assert result["series"]["total_books"] == 7
        assert result["series_position"] == "1.0"

    @pytest.mark.asyncio
    async def test_flush_view_counts_to_db(self, mock_session):
        pending_counts = {
            1: {"count": 10, "last_viewed": 1234567890},
            2: {"count": 5, "last_viewed": 1234567891}
        }

        with patch('app.cache.get_pending_view_counts', return_value=pending_counts), \
             patch('app.cache.clear_view_counts') as mock_clear:

            await book_service.flush_view_counts_to_db(mock_session)

            assert mock_session.execute.call_count == 2
            mock_session.commit.assert_called_once()
            mock_clear.assert_called_once_with("book", [1, 2])

    @pytest.mark.asyncio
    async def test_flush_view_counts_to_db_empty(self, mock_session):
        with patch('app.cache.get_pending_view_counts', return_value=None):
            await book_service.flush_view_counts_to_db(mock_session)

            mock_session.execute.assert_not_called()
            mock_session.commit.assert_not_called()
