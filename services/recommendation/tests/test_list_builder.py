import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.services.list_builder as list_builder
from tests.conftest import make_book_row, make_author_row, make_execute_result


class TestCategoryRegistry:
    def test_all_19_categories_defined(self):
        assert len(list_builder.CATEGORIES) == 19

    def test_all_category_keys_unique(self):
        keys = [c["key"] for c in list_builder.CATEGORIES]
        assert len(keys) == len(set(keys))

    def test_category_keys_match_registry(self):
        for cat in list_builder.CATEGORIES:
            assert cat["key"] in list_builder.CATEGORY_KEYS

    def test_all_categories_have_required_fields(self):
        for cat in list_builder.CATEGORIES:
            assert "key" in cat
            assert "display_name" in cat
            assert "item_type" in cat
            assert "build_fn" in cat
            assert cat["item_type"] in ("book", "author")

    def test_book_categories_count(self):
        book_cats = [c for c in list_builder.CATEGORIES if c["item_type"] == "book"]
        assert len(book_cats) == 17

    def test_author_categories_count(self):
        author_cats = [c for c in list_builder.CATEGORIES if c["item_type"] == "author"]
        assert len(author_cats) == 2


class TestRowToBookItem:
    def test_converts_row_correctly(self):
        row = make_book_row()
        item = list_builder._row_to_book_item(row, 500.0)

        assert item["book_id"] == 1
        assert item["title"] == "Test Book"
        assert item["slug"] == "test-book"
        assert item["language"] == "en"
        assert item["primary_cover_url"] == "https://example.com/cover.jpg"
        assert item["avg_rating"] == "4.20"
        assert item["rating_count"] == 10
        assert item["author_names"] == ["Author One"]
        assert item["author_slugs"] == ["author-one"]
        assert item["score"] == 500.0

    def test_handles_none_values(self):
        row = make_book_row(
            title=None,
            primary_cover_url=None,
            avg_rating=None,
            rating_count=None,
            author_names=None,
            author_slugs=None,
        )
        row.author_names = None
        row.author_slugs = None
        item = list_builder._row_to_book_item(row, 0.0)

        assert item["title"] == ""
        assert item["primary_cover_url"] == ""
        assert item["avg_rating"] == ""
        assert item["rating_count"] == 0
        assert item["author_names"] == []
        assert item["author_slugs"] == []


class TestBuildMostRead:
    @pytest.mark.asyncio
    async def test_returns_book_items(self, mock_session):
        rows = [make_book_row(book_id=1, score=9000), make_book_row(book_id=2, score=5000)]
        mock_session.execute.return_value = make_execute_result(rows)

        result = await list_builder._build_most_read(mock_session, 50)

        assert len(result) == 2
        assert result[0]["book_id"] == 1
        assert result[0]["score"] == 9000.0
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_rows(self, mock_session):
        mock_session.execute.return_value = make_execute_result([])
        result = await list_builder._build_most_read(mock_session, 50)
        assert result == []


class TestBuildHighestRated:
    @pytest.mark.asyncio
    async def test_returns_book_items(self, mock_session):
        row = make_book_row(book_id=1, avg_rating="4.80", rating_count=10, score=4.80)
        mock_session.execute.return_value = make_execute_result([row])

        result = await list_builder._build_highest_rated(mock_session, 50)

        assert len(result) == 1
        assert result[0]["avg_rating"] == "4.80"


class TestBuildSubRatingQuery:
    def test_query_contains_dimension(self):
        query = list_builder._build_sub_rating_query("humor")
        assert "humor" in query

    def test_query_has_minimum_count_filter(self):
        query = list_builder._build_sub_rating_query("writing_quality")
        assert ">= 3" in query


class TestBuildTopAuthors:
    @pytest.mark.asyncio
    async def test_returns_author_items(self, mock_session):
        row = make_author_row(author_id=1, score=50000)
        mock_session.execute.return_value = make_execute_result([row])

        result = await list_builder._build_top_authors(mock_session, 50)

        assert len(result) == 1
        assert result[0]["author_id"] == 1
        assert result[0]["score"] == 50000.0
        assert result[0]["book_count"] == 5

    @pytest.mark.asyncio
    async def test_handles_none_photo_url(self, mock_session):
        row = make_author_row()
        row.photo_url = None
        mock_session.execute.return_value = make_execute_result([row])

        result = await list_builder._build_top_authors(mock_session, 50)

        assert result[0]["photo_url"] == ""


class TestRefreshAll:
    @pytest.mark.asyncio
    async def test_caches_all_categories(self, mock_session):
        mock_session.execute.return_value = make_execute_result([])

        with patch("app.cache.set_cached", new_callable=AsyncMock) as mock_set:
            with patch("app.config.settings") as mock_settings:
                mock_settings.list_default_size = 50
                mock_settings.cache_recommendation_ttl = 86400
                await list_builder.refresh_all(mock_session)

        assert mock_set.call_count == 19

    @pytest.mark.asyncio
    async def test_continues_on_category_error(self, mock_session):
        call_count = 0

        async def failing_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("DB error")
            return make_execute_result([])

        mock_session.execute.side_effect = failing_execute

        with patch("app.cache.set_cached", new_callable=AsyncMock):
            with patch("app.config.settings") as mock_settings:
                mock_settings.list_default_size = 50
                mock_settings.cache_recommendation_ttl = 86400
                await list_builder.refresh_all(mock_session)

    @pytest.mark.asyncio
    async def test_cache_key_format(self, mock_session):
        mock_session.execute.return_value = make_execute_result([])

        cached_keys = []

        async def capture_set(key, value, ttl):
            cached_keys.append(key)
            return True

        with patch("app.cache.set_cached", side_effect=capture_set):
            with patch("app.config.settings") as mock_settings:
                mock_settings.list_default_size = 50
                mock_settings.cache_recommendation_ttl = 86400
                await list_builder.refresh_all(mock_session)

        assert all(k.startswith("rec:") for k in cached_keys)

    @pytest.mark.asyncio
    async def test_payload_structure_for_book_category(self, mock_session):
        row = make_book_row(book_id=42)
        mock_session.execute.return_value = make_execute_result([row])

        payloads = {}

        async def capture_set(key, value, ttl):
            payloads[key] = value
            return True

        with patch("app.cache.set_cached", side_effect=capture_set):
            with patch("app.config.settings") as mock_settings:
                mock_settings.list_default_size = 50
                mock_settings.cache_recommendation_ttl = 86400
                await list_builder.refresh_all(mock_session)

        most_read = payloads.get("rec:most_read")
        assert most_read is not None
        assert most_read["item_type"] == "book"
        assert "book_items" in most_read
        assert most_read["total"] >= 0

    @pytest.mark.asyncio
    async def test_payload_structure_for_author_category(self, mock_session):
        row = make_author_row(author_id=7)
        mock_session.execute.return_value = make_execute_result([row])

        payloads = {}

        async def capture_set(key, value, ttl):
            payloads[key] = value
            return True

        with patch("app.cache.set_cached", side_effect=capture_set):
            with patch("app.config.settings") as mock_settings:
                mock_settings.list_default_size = 50
                mock_settings.cache_recommendation_ttl = 86400
                await list_builder.refresh_all(mock_session)

        top_authors = payloads.get("rec:top_authors")
        assert top_authors is not None
        assert top_authors["item_type"] == "author"
        assert "author_items" in top_authors
