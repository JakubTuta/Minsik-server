from unittest.mock import AsyncMock

import app.services.comment_service as comment_service
import pytest
from tests.conftest import make_list_result, make_scalar_result


class TestCreateComment:
    @pytest.mark.asyncio
    async def test_create_success(self, mock_session, mock_comment):
        mock_session.refresh = AsyncMock()
        result = await comment_service.create_comment(
            mock_session, 10, 100, "Really enjoyed this book!", False
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_spoiler_comment(self, mock_session, mock_comment):
        result = await comment_service.create_comment(
            mock_session, 10, 100, "The ending was surprising", True
        )
        added = mock_session.add.call_args[0][0]
        assert added.is_spoiler is True


class TestUpdateComment:
    @pytest.mark.asyncio
    async def test_update_success(self, mock_session, mock_comment):
        mock_session.execute.return_value = make_scalar_result(mock_comment)
        result = await comment_service.update_comment(
            mock_session, 1, 10, "Updated body", False
        )
        assert mock_comment.body == "Updated body"
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self, mock_session):
        mock_session.execute.return_value = make_scalar_result(None)
        with pytest.raises(ValueError, match="not_found"):
            await comment_service.update_comment(
                mock_session, 999, 10, "Updated body", False
            )

    @pytest.mark.asyncio
    async def test_update_spoiler_flag(self, mock_session, mock_comment):
        mock_session.execute.return_value = make_scalar_result(mock_comment)
        await comment_service.update_comment(mock_session, 1, 10, "Body", True)
        assert mock_comment.is_spoiler is True


class TestDeleteComment:
    @pytest.mark.asyncio
    async def test_delete_removes_row(self, mock_session, mock_comment):
        mock_session.execute.return_value = make_scalar_result(mock_comment)
        await comment_service.delete_comment(mock_session, 1, 10)
        mock_session.execute.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, mock_session):
        mock_session.execute.return_value = make_scalar_result(None)
        with pytest.raises(ValueError, match="not_found"):
            await comment_service.delete_comment(mock_session, 999, 10)


class TestGetBookComments:
    @pytest.mark.asyncio
    async def test_returns_items_and_count(self, mock_session, mock_comment):
        count_result, items_result = make_list_result([mock_comment], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_book_comments(
            mock_session, 100, 10, 0, "desc", False
        )
        assert total == 1
        assert rows == [mock_comment]

    @pytest.mark.asyncio
    async def test_include_spoilers_flag(self, mock_session, mock_comment):
        count_result, items_result = make_list_result([mock_comment], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_book_comments(
            mock_session, 100, 10, 0, "desc", True
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_asc_order(self, mock_session, mock_comment):
        count_result, items_result = make_list_result([mock_comment], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_book_comments(
            mock_session, 100, 10, 0, "asc", False
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        count_result, items_result = make_list_result([], 0)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_book_comments(
            mock_session, 100, 10, 0, "desc", False
        )
        assert total == 0
        assert rows == []


class TestGetUserComments:
    @pytest.mark.asyncio
    async def test_returns_user_comments(self, mock_session, mock_comment):
        count_result, items_result = make_list_result([mock_comment], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_user_comments(
            mock_session, 10, 10, 0, "created_at", "desc", None
        )
        assert total == 1
        assert rows == [mock_comment]

    @pytest.mark.asyncio
    async def test_with_book_id_filter(self, mock_session, mock_comment):
        count_result, items_result = make_list_result([mock_comment], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_user_comments(
            mock_session, 10, 10, 0, "created_at", "desc", 100
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_sort_by_updated_at(self, mock_session, mock_comment):
        count_result, items_result = make_list_result([mock_comment], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await comment_service.get_user_comments(
            mock_session, 10, 10, 0, "updated_at", "asc", None
        )
        assert total == 1
