import pytest
from unittest.mock import AsyncMock, MagicMock
import app.services.bookshelf_service as bookshelf_service
from tests.conftest import make_scalar_result, make_list_result


class TestUpsertBookshelf:
    @pytest.mark.asyncio
    async def test_upsert_success(self, mock_session, mock_bookshelf):
        mock_session.execute.return_value = make_scalar_result(mock_bookshelf)
        result = await bookshelf_service.upsert_bookshelf(mock_session, 10, 100, "reading")
        assert result == mock_bookshelf
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_invalid_status_raises(self, mock_session):
        with pytest.raises(ValueError, match="invalid_status"):
            await bookshelf_service.upsert_bookshelf(mock_session, 10, 100, "invalid_value")

    @pytest.mark.asyncio
    async def test_upsert_all_valid_statuses(self, mock_session, mock_bookshelf):
        for status in ("want_to_read", "reading", "read", "abandoned"):
            mock_session.execute.return_value = make_scalar_result(mock_bookshelf)
            result = await bookshelf_service.upsert_bookshelf(mock_session, 10, 100, status)
            assert result == mock_bookshelf


class TestGetBookshelf:
    @pytest.mark.asyncio
    async def test_get_success(self, mock_session, mock_bookshelf):
        mock_session.execute.return_value = make_scalar_result(mock_bookshelf)
        result = await bookshelf_service.get_bookshelf(mock_session, 10, 100)
        assert result == mock_bookshelf

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self, mock_session):
        mock_session.execute.return_value = make_scalar_result(None)
        with pytest.raises(ValueError, match="not_found"):
            await bookshelf_service.get_bookshelf(mock_session, 10, 999)


class TestGetUserBookshelves:
    @pytest.mark.asyncio
    async def test_returns_items_and_count(self, mock_session, mock_bookshelf):
        count_result, items_result = make_list_result([mock_bookshelf], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await bookshelf_service.get_user_bookshelves(
            mock_session, 10, 10, 0, "", False, "created_at", "desc"
        )
        assert total == 1
        assert rows == [mock_bookshelf]

    @pytest.mark.asyncio
    async def test_with_status_filter(self, mock_session, mock_bookshelf):
        count_result, items_result = make_list_result([mock_bookshelf], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await bookshelf_service.get_user_bookshelves(
            mock_session, 10, 10, 0, "reading", False, "created_at", "desc"
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_favourites_only_filter(self, mock_session, mock_bookshelf):
        mock_bookshelf.is_favorite = True
        count_result, items_result = make_list_result([mock_bookshelf], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await bookshelf_service.get_user_bookshelves(
            mock_session, 10, 10, 0, "", True, "created_at", "desc"
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        count_result, items_result = make_list_result([], 0)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await bookshelf_service.get_user_bookshelves(
            mock_session, 10, 10, 0, "", False, "created_at", "desc"
        )
        assert total == 0
        assert rows == []

    @pytest.mark.asyncio
    async def test_asc_sort(self, mock_session, mock_bookshelf):
        count_result, items_result = make_list_result([mock_bookshelf], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await bookshelf_service.get_user_bookshelves(
            mock_session, 10, 10, 0, "", False, "updated_at", "asc"
        )
        assert total == 1


class TestToggleFavourite:
    @pytest.mark.asyncio
    async def test_set_favourite(self, mock_session, mock_bookshelf):
        mock_bookshelf.is_favorite = True
        mock_session.execute.return_value = make_scalar_result(mock_bookshelf)
        result = await bookshelf_service.toggle_favourite(mock_session, 10, 100, True)
        assert result.is_favorite is True
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_unset_favourite(self, mock_session, mock_bookshelf):
        mock_bookshelf.is_favorite = False
        mock_session.execute.return_value = make_scalar_result(mock_bookshelf)
        result = await bookshelf_service.toggle_favourite(mock_session, 10, 100, False)
        assert result.is_favorite is False
        mock_session.commit.assert_called_once()
