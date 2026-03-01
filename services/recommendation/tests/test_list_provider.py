import pytest
from unittest.mock import AsyncMock, patch

import app.services.list_provider as list_provider
import app.services.list_builder as list_builder


SAMPLE_BOOK_PAYLOAD = {
    "category": "most_read",
    "display_name": "Most Read Books",
    "item_type": "book",
    "book_items": [
        {
            "book_id": 1,
            "title": "Book A",
            "slug": "book-a",
            "language": "en",
            "primary_cover_url": "https://example.com/a.jpg",
            "author_names": ["Author One"],
            "author_slugs": ["author-one"],
            "avg_rating": "4.50",
            "rating_count": 100,
            "score": 9000.0,
        },
        {
            "book_id": 2,
            "title": "Book B",
            "slug": "book-b",
            "language": "en",
            "primary_cover_url": "https://example.com/b.jpg",
            "author_names": ["Author Two"],
            "author_slugs": ["author-two"],
            "avg_rating": "4.00",
            "rating_count": 50,
            "score": 5000.0,
        },
    ],
    "total": 2,
}

SAMPLE_AUTHOR_PAYLOAD = {
    "category": "top_authors",
    "display_name": "Most Read Authors",
    "item_type": "author",
    "author_items": [
        {
            "author_id": 10,
            "name": "Famous Author",
            "slug": "famous-author",
            "photo_url": "https://example.com/photo.jpg",
            "book_count": 12,
            "score": 50000.0,
        }
    ],
    "total": 1,
}


class TestGetList:
    @pytest.mark.asyncio
    async def test_returns_cached_data(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            result = await list_provider.get_list("most_read", 20, 0)

        assert result is not None
        assert result["category"] == "most_read"
        assert result["item_type"] == "book"
        assert len(result["book_items"]) == 2
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_cache_empty(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=None):
            result = await list_provider.get_list("most_read", 20, 0)

        assert result is None

    @pytest.mark.asyncio
    async def test_applies_limit(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            result = await list_provider.get_list("most_read", 1, 0)

        assert len(result["book_items"]) == 1
        assert result["book_items"][0]["book_id"] == 1

    @pytest.mark.asyncio
    async def test_applies_offset(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            result = await list_provider.get_list("most_read", 20, 1)

        assert len(result["book_items"]) == 1
        assert result["book_items"][0]["book_id"] == 2

    @pytest.mark.asyncio
    async def test_total_reflects_full_list_not_page(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            result = await list_provider.get_list("most_read", 1, 0)

        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_offset_beyond_end_returns_empty(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            result = await list_provider.get_list("most_read", 20, 100)

        assert result["book_items"] == []
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_author_payload_uses_author_items_key(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_AUTHOR_PAYLOAD):
            result = await list_provider.get_list("top_authors", 20, 0)

        assert "author_items" in result
        assert result["author_items"][0]["author_id"] == 10

    @pytest.mark.asyncio
    async def test_cache_key_uses_rec_prefix(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=None) as mock_get:
            await list_provider.get_list("most_read", 20, 0)

        mock_get.assert_called_once_with("rec:most_read")


class TestGetHomePage:
    @pytest.mark.asyncio
    async def test_returns_configured_categories(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            with patch("app.config.settings") as mock_settings:
                mock_settings.home_book_categories = "most_read"
                mock_settings.home_author_categories = ""
                result = await list_provider.get_home_page(20)

        assert len(result) == 1
        assert result[0]["category"] == "most_read"

    @pytest.mark.asyncio
    async def test_skips_unavailable_categories(self):
        call_count = 0

        async def selective_cache(key):
            nonlocal call_count
            call_count += 1
            if "most_read" in key:
                return SAMPLE_BOOK_PAYLOAD
            return None

        with patch("app.cache.get_cached", side_effect=selective_cache):
            with patch("app.config.settings") as mock_settings:
                mock_settings.home_book_categories = "most_read,highest_rated"
                mock_settings.home_author_categories = ""
                result = await list_provider.get_home_page(20)

        assert len(result) == 1
        assert result[0]["category"] == "most_read"

    @pytest.mark.asyncio
    async def test_includes_book_and_author_categories(self):
        async def get_by_key(key):
            if "most_read" in key:
                return SAMPLE_BOOK_PAYLOAD
            if "top_authors" in key:
                return SAMPLE_AUTHOR_PAYLOAD
            return None

        with patch("app.cache.get_cached", side_effect=get_by_key):
            with patch("app.config.settings") as mock_settings:
                mock_settings.home_book_categories = "most_read"
                mock_settings.home_author_categories = "top_authors"
                result = await list_provider.get_home_page(20)

        assert len(result) == 2
        item_types = {r["item_type"] for r in result}
        assert item_types == {"book", "author"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_cache(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=None):
            with patch("app.config.settings") as mock_settings:
                mock_settings.home_book_categories = "most_read,highest_rated"
                mock_settings.home_author_categories = "top_authors"
                result = await list_provider.get_home_page(20)

        assert result == []

    @pytest.mark.asyncio
    async def test_limits_items_per_category(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            with patch("app.config.settings") as mock_settings:
                mock_settings.home_book_categories = "most_read"
                mock_settings.home_author_categories = ""
                result = await list_provider.get_home_page(1)

        assert len(result[0]["book_items"]) == 1

    @pytest.mark.asyncio
    async def test_handles_whitespace_in_config(self):
        with patch("app.cache.get_cached", new_callable=AsyncMock, return_value=SAMPLE_BOOK_PAYLOAD):
            with patch("app.config.settings") as mock_settings:
                mock_settings.home_book_categories = "most_read, highest_rated "
                mock_settings.home_author_categories = ""
                result = await list_provider.get_home_page(20)

        assert len(result) == 2


class TestGetAvailableCategories:
    def test_returns_all_categories(self):
        result = list_provider.get_available_categories()
        assert len(result) == len(list_builder.CATEGORIES)

    def test_each_entry_has_required_fields(self):
        result = list_provider.get_available_categories()
        for entry in result:
            assert "category" in entry
            assert "display_name" in entry
            assert "item_type" in entry

    def test_category_keys_match_builder(self):
        result = list_provider.get_available_categories()
        returned_keys = {r["category"] for r in result}
        builder_keys = {c["key"] for c in list_builder.CATEGORIES}
        assert returned_keys == builder_keys

    def test_item_types_are_valid(self):
        result = list_provider.get_available_categories()
        for entry in result:
            assert entry["item_type"] in ("book", "author")
