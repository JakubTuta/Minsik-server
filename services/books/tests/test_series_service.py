import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import app.services.series_service as series_service


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_series():
    series = MagicMock()
    series.series_id = 1
    series.name = "Harry Potter"
    series.slug = "harry-potter"
    series.description = "A magical series"
    series.view_count = 5000
    series.last_viewed_at = None
    series.created_at = None
    series.updated_at = None
    return series


@pytest.fixture
def mock_book():
    book = MagicMock()
    book.book_id = 1
    book.title = "Harry Potter and the Philosopher's Stone"
    book.slug = "harry-potter-philosophers-stone"
    book.description = "The first book"
    book.original_publication_year = 1997
    book.primary_cover_url = "http://example.com/cover.jpg"
    book.rating_count = 1000
    book.avg_rating = 4.7
    book.view_count = 3000
    book.series_position = 1.0

    genre = MagicMock()
    genre.genre_id = 1
    genre.name = "Fantasy"
    genre.slug = "fantasy"
    book.genres = [genre]

    return book


class TestSeriesService:
    @pytest.mark.asyncio
    async def test_get_series_by_slug_cache_hit(self, mock_session):
        cached_series = {
            "series_id": 1,
            "name": "Harry Potter",
            "slug": "harry-potter",
            "total_books": 7
        }

        with patch('app.cache.get_cached', return_value=cached_series), \
             patch('app.cache.increment_view_count') as mock_track:

            result = await series_service.get_series_by_slug(mock_session, "harry-potter")

            assert result == cached_series
            mock_track.assert_called_once_with("series", 1)

    @pytest.mark.asyncio
    async def test_get_series_by_slug_cache_miss(self, mock_session, mock_series):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_series

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 7

        mock_session.execute.side_effect = [mock_result, mock_count_result]

        with patch('app.cache.get_cached', return_value=None), \
             patch('app.cache.set_cached') as mock_set_cache, \
             patch('app.cache.increment_view_count'):

            result = await series_service.get_series_by_slug(mock_session, "harry-potter")

            assert result is not None
            assert result["name"] == "Harry Potter"
            assert result["slug"] == "harry-potter"
            assert result["total_books"] == 7
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_series_by_slug_not_found(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch('app.cache.get_cached', return_value=None):
            result = await series_service.get_series_by_slug(mock_session, "nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_series_books_cache_hit(self, mock_session):
        cached_data = {
            "books": [{"book_id": 1, "title": "Book 1", "series_position": "1.0"}],
            "total": 7
        }

        with patch('app.cache.get_cached', return_value=cached_data):
            books, total = await series_service.get_series_books(
                mock_session, "harry-potter", 10, 0
            )

            assert books == cached_data["books"]
            assert total == 7

    @pytest.mark.asyncio
    async def test_get_series_books_cache_miss(self, mock_session, mock_series, mock_book):
        mock_series_result = MagicMock()
        mock_series_result.scalar_one_or_none.return_value = mock_series

        mock_books_result = MagicMock()
        mock_books_result.scalars.return_value.all.return_value = [mock_book]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 7

        mock_session.execute.side_effect = [
            mock_series_result,
            mock_books_result,
            mock_count_result
        ]

        with patch('app.cache.get_cached', return_value=None), \
             patch('app.cache.set_cached') as mock_set_cache:

            books, total = await series_service.get_series_books(
                mock_session, "harry-potter", 10, 0
            )

            assert len(books) == 1
            assert books[0]["title"] == "Harry Potter and the Philosopher's Stone"
            assert books[0]["series_position"] == "1.0"
            assert total == 7
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_series_books_series_not_found(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with patch('app.cache.get_cached', return_value=None):
            books, total = await series_service.get_series_books(
                mock_session, "nonexistent", 10, 0
            )

            assert books == []
            assert total == 0

    @pytest.mark.asyncio
    async def test_get_series_books_with_pagination(self, mock_session, mock_series, mock_book):
        mock_series_result = MagicMock()
        mock_series_result.scalar_one_or_none.return_value = mock_series

        mock_books_result = MagicMock()
        mock_books_result.scalars.return_value.all.return_value = [mock_book]

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 7

        mock_session.execute.side_effect = [
            mock_series_result,
            mock_books_result,
            mock_count_result
        ]

        with patch('app.cache.get_cached', return_value=None), \
             patch('app.cache.set_cached'):

            books, total = await series_service.get_series_books(
                mock_session, "harry-potter", 5, 2
            )

            assert len(books) == 1
            assert total == 7

    def test_series_to_dict(self, mock_series):
        result = series_service._series_to_dict(mock_series, 7)

        assert result["series_id"] == 1
        assert result["name"] == "Harry Potter"
        assert result["slug"] == "harry-potter"
        assert result["description"] == "A magical series"
        assert result["total_books"] == 7
        assert result["view_count"] == 5000
