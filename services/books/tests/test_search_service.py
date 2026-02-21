import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.search_service as search_service
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_cache():
    with patch("app.cache.get_cached", return_value=None), patch(
        "app.cache.set_cached", return_value=None
    ):
        yield


class TestSearchBooksAndAuthors:
    @pytest.mark.asyncio
    async def test_search_all_types(self, mock_session, mock_cache):
        with patch(
            "app.services.search_service._search_books_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_authors_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_series_es", return_value=([], 0)
        ):

            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="all"
            )

            assert isinstance(results, list)
            assert total == 0

    @pytest.mark.asyncio
    async def test_search_books_only(self, mock_session, mock_cache):
        mock_books = [
            {
                "type": "book",
                "id": 1,
                "title": "Test Book",
                "slug": "test-book",
                "cover_url": "",
                "authors": ["Test Author"],
                "relevance_score": 0.9,
                "view_count": 100,
            }
        ]

        with patch(
            "app.services.search_service._search_books_es", return_value=(mock_books, 1)
        ), patch(
            "app.services.search_service._search_authors_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_series_es", return_value=([], 0)
        ):

            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="books"
            )

            assert len(results) == 1
            assert results[0]["type"] == "book"
            assert total == 1

    @pytest.mark.asyncio
    async def test_search_with_author_expansion(self, mock_session, mock_cache):
        mock_authors = [
            {
                "type": "author",
                "id": 1,
                "title": "Test Author",
                "slug": "test-author",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.8,
                "view_count": 50,
            }
        ]

        mock_author_books = [
            {
                "type": "book",
                "id": 1,
                "title": "Author's Book",
                "slug": "authors-book",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.4,
                "view_count": 30,
            }
        ]

        with patch(
            "app.services.search_service._search_books_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_authors_es",
            return_value=(mock_authors, 1),
        ), patch(
            "app.services.search_service._search_series_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._get_author_top_books",
            return_value=mock_author_books,
        ):

            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="authors"
            )

            assert len(results) == 2
            assert any(r["type"] == "author" for r in results)
            assert any(r["type"] == "book" for r in results)

    @pytest.mark.asyncio
    async def test_search_series_with_expansion(self, mock_session, mock_cache):
        mock_series = [
            {
                "type": "series",
                "id": 1,
                "title": "Test Series",
                "slug": "test-series",
                "cover_url": "",
                "authors": ["3 books"],
                "relevance_score": 0.85,
                "view_count": 75,
            }
        ]

        mock_series_books = [
            {
                "type": "book",
                "id": 1,
                "title": "Series Book 1",
                "slug": "series-book-1",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.4,
                "view_count": 20,
            }
        ]

        with patch(
            "app.services.search_service._search_books_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_authors_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_series_es",
            return_value=(mock_series, 1),
        ), patch(
            "app.services.search_service._get_series_top_books",
            return_value=mock_series_books,
        ):

            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="series"
            )

            assert len(results) == 2
            assert any(r["type"] == "series" for r in results)
            assert any(r["type"] == "book" for r in results)

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_relevance(self, mock_session, mock_cache):
        mock_results = [
            {
                "type": "book",
                "id": 1,
                "title": "Book 1",
                "slug": "book-1",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.5,
                "view_count": 10,
            },
            {
                "type": "book",
                "id": 2,
                "title": "Book 2",
                "slug": "book-2",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.9,
                "view_count": 50,
            },
            {
                "type": "book",
                "id": 3,
                "title": "Book 3",
                "slug": "book-3",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.7,
                "view_count": 30,
            },
        ]

        with patch(
            "app.services.search_service._search_books_es",
            return_value=(mock_results, 3),
        ), patch(
            "app.services.search_service._search_authors_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_series_es", return_value=([], 0)
        ):

            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=10, offset=0, type_filter="books"
            )

            assert results[0]["relevance_score"] == 0.9
            assert results[1]["relevance_score"] == 0.7
            assert results[2]["relevance_score"] == 0.5

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, mock_session, mock_cache):
        mock_results = [
            {
                "type": "book",
                "id": i,
                "title": f"Book {i}",
                "slug": f"book-{i}",
                "cover_url": "",
                "authors": [],
                "relevance_score": 0.8,
                "view_count": 10,
            }
            for i in range(20)
        ]

        with patch(
            "app.services.search_service._search_books_es",
            return_value=(mock_results, 20),
        ), patch(
            "app.services.search_service._search_authors_es", return_value=([], 0)
        ), patch(
            "app.services.search_service._search_series_es", return_value=([], 0)
        ):

            results, total = await search_service.search_books_and_authors(
                mock_session, query="test", limit=5, offset=0, type_filter="books"
            )

            assert len(results) == 5
            assert total == 20
