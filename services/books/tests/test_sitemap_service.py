import datetime
from unittest.mock import AsyncMock, MagicMock

import app.services.sitemap_service as sitemap_service
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


def make_rows_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def make_count_result(count):
    result = MagicMock()
    result.scalar_one.return_value = count
    return result


class TestSitemapService:
    @pytest.mark.asyncio
    async def test_invalid_entity_raises(self, mock_session):
        with pytest.raises(ValueError):
            await sitemap_service.list_sitemap_slugs(mock_session, "users")

    @pytest.mark.asyncio
    async def test_returns_items_with_isoformat_updated_at(self, mock_session):
        updated = datetime.datetime(2026, 1, 1, 12, 0, 0)
        mock_session.execute.side_effect = [
            make_rows_result([("the-hobbit", updated), ("dune", None)]),
            make_count_result(2),
        ]

        items, total = await sitemap_service.list_sitemap_slugs(
            mock_session, "books", limit=10, offset=0
        )

        assert total == 2
        assert items[0] == {"slug": "the-hobbit", "updated_at": "2026-01-01T12:00:00"}
        assert items[1] == {"slug": "dune", "updated_at": ""}

    @pytest.mark.asyncio
    async def test_skips_count_for_nonzero_offset(self, mock_session):
        mock_session.execute.side_effect = [
            make_rows_result([("jrr-tolkien", None)]),
        ]

        items, total = await sitemap_service.list_sitemap_slugs(
            mock_session, "authors", limit=10, offset=10
        )

        assert total == 0
        assert items[0]["slug"] == "jrr-tolkien"
        assert mock_session.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_series_entity_supported(self, mock_session):
        mock_session.execute.side_effect = [
            make_rows_result([("the-lord-of-the-rings", None)]),
            make_count_result(1),
        ]

        items, total = await sitemap_service.list_sitemap_slugs(
            mock_session, "series"
        )

        assert total == 1
        assert items[0]["slug"] == "the-lord-of-the-rings"
