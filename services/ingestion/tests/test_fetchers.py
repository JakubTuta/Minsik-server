import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.fetchers import OpenLibraryFetcher, GoogleBooksFetcher


@pytest.mark.asyncio
@pytest.mark.unit
async def test_open_library_fetch_books(mock_open_library_response, mock_open_library_work, mock_open_library_author):
    async with OpenLibraryFetcher() as fetcher:
        fetcher._fetch_with_retry = AsyncMock(side_effect=[
            mock_open_library_response,
            mock_open_library_work,
            mock_open_library_author
        ])

        books = await fetcher.fetch_books(count=1, language="en")

        assert len(books) > 0
        assert books[0]["title"] == "Neuromancer"
        assert books[0]["language"] == "en"
        assert len(books[0]["authors"]) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_open_library_parse_book_data(mock_open_library_response, mock_open_library_work, mock_open_library_author):
    async with OpenLibraryFetcher() as fetcher:
        fetcher._fetch_work_details = AsyncMock(return_value=mock_open_library_work)
        fetcher._fetch_author_details = AsyncMock(return_value=mock_open_library_author)

        work = mock_open_library_response["works"][0]
        parsed = await fetcher.parse_book_data(work, "en")

        assert parsed is not None
        assert parsed["title"] == "Neuromancer"
        assert parsed["language"] == "en"
        assert parsed["slug"] == "neuromancer"
        assert len(parsed["authors"]) > 0
        assert parsed["authors"][0]["name"] == "William Gibson"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_open_library_cover_url():
    async with OpenLibraryFetcher() as fetcher:
        cover_url = fetcher._get_cover_url(12345, "L")
        assert cover_url == "https://covers.openlibrary.org/b/id/12345-L.jpg"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_google_books_fetch_books(mock_google_books_response):
    async with GoogleBooksFetcher() as fetcher:
        fetcher._fetch_with_retry = AsyncMock(return_value=mock_google_books_response)

        books = await fetcher.fetch_books(count=1, language="en")

        assert len(books) > 0
        assert books[0]["title"] == "Neuromancer"
        assert books[0]["language"] == "en"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_google_books_parse_book_data(mock_google_books_response):
    async with GoogleBooksFetcher() as fetcher:
        item = mock_google_books_response["items"][0]
        parsed = await fetcher.parse_book_data(item, "en")

        assert parsed is not None
        assert parsed["title"] == "Neuromancer"
        assert parsed["language"] == "en"
        assert parsed["slug"] == "neuromancer"
        assert len(parsed["authors"]) > 0
        assert parsed["authors"][0]["name"] == "William Gibson"
        assert parsed["google_books_id"] == "gb123"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_google_books_extract_formats():
    async with GoogleBooksFetcher() as fetcher:
        raw_data = {
            "accessInfo": {
                "epub": {"isAvailable": True},
                "pdf": {"isAvailable": False}
            },
            "volumeInfo": {
                "printType": "BOOK"
            }
        }

        formats = fetcher._extract_formats(raw_data)

        assert "ebook" in formats
        assert "paperback" in formats


@pytest.mark.asyncio
@pytest.mark.unit
async def test_fetcher_retry_on_rate_limit():
    with patch('httpx.AsyncClient') as mock_client:
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"data": "success"}

        mock_client.return_value.get = AsyncMock(side_effect=[
            mock_response_429,
            mock_response_200
        ])
        mock_client.return_value.aclose = AsyncMock()

        async with OpenLibraryFetcher() as fetcher:
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await fetcher._fetch_with_retry("http://example.com")

                assert result == {"data": "success"}
