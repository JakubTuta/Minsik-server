import datetime
import types
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


def make_book_row(slug, language, updated_at, work_id="W1"):
    return types.SimpleNamespace(
        slug=slug, language=language, updated_at=updated_at, work_id=work_id
    )


class TestSitemapService:
    @pytest.mark.asyncio
    async def test_invalid_entity_raises(self, mock_session):
        with pytest.raises(ValueError):
            await sitemap_service.list_sitemap_slugs(mock_session, "users")

    @pytest.mark.asyncio
    async def test_returns_items_with_isoformat_updated_at(self, mock_session):
        updated = datetime.datetime(2026, 1, 1, 12, 0, 0)
        mock_session.execute.side_effect = [
            make_rows_result([
                make_book_row("the-hobbit", "en", updated),
                make_book_row("dune", "en", None),
            ]),
            make_count_result(2),
        ]

        items, total = await sitemap_service.list_sitemap_slugs(
            mock_session, "books", limit=10, offset=0
        )

        assert total == 2
        assert items[0] == {
            "slug": "the-hobbit",
            "language": "en",
            "work_id": "W1",
            "updated_at": "2026-01-01T12:00:00",
        }
        assert items[1] == {
            "slug": "dune", "language": "en", "work_id": "W1", "updated_at": "",
        }

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
    async def test_every_edition_of_a_work_is_listed(self, mock_session):
        # Each translation needs a URL of its own to be indexable at all.
        updated = datetime.datetime(2026, 1, 1, 12, 0, 0)
        mock_session.execute.side_effect = [
            make_rows_result([
                make_book_row("the-witcher", "en", updated),
                make_book_row("wiedzmin", "pl", updated),
            ]),
            make_count_result(1),
        ]

        items, total = await sitemap_service.list_sitemap_slugs(
            mock_session, "books", limit=10, offset=0
        )

        assert [item["language"] for item in items] == ["en", "pl"]
        assert total == 1

    def test_books_paging_counts_works_not_editions(self):
        # Otherwise one heavily translated book eats a whole page of the cap.
        assert "GROUP BY work_id" in sitemap_service._BOOKS_SITEMAP_QUERY
        assert "LIMIT :limit OFFSET :offset" in sitemap_service._BOOKS_SITEMAP_QUERY.split(
            "SELECT b.slug"
        )[0]

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
