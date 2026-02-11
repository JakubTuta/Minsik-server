import pytest
from unittest.mock import MagicMock
import app.services.note_service as note_service
from tests.conftest import make_scalar_result, make_list_result


class TestCreateNote:
    @pytest.mark.asyncio
    async def test_create_with_page_number(self, mock_session, mock_note):
        result = await note_service.create_note(
            mock_session, 10, 100, "Remember this passage", 42, False
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.page_number == 42

    @pytest.mark.asyncio
    async def test_create_without_page_number(self, mock_session, mock_note):
        result = await note_service.create_note(
            mock_session, 10, 100, "A general note", None, False
        )
        added = mock_session.add.call_args[0][0]
        assert added.page_number is None

    @pytest.mark.asyncio
    async def test_create_spoiler_note(self, mock_session, mock_note):
        result = await note_service.create_note(
            mock_session, 10, 100, "Spoiler note text", None, True
        )
        added = mock_session.add.call_args[0][0]
        assert added.is_spoiler is True


class TestUpdateNote:
    @pytest.mark.asyncio
    async def test_update_success(self, mock_session, mock_note):
        mock_session.execute.return_value = make_scalar_result(mock_note)
        result = await note_service.update_note(
            mock_session, 1, 10, "Updated text", 50, False
        )
        assert mock_note.note_text == "Updated text"
        assert mock_note.page_number == 50
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found_raises(self, mock_session):
        mock_session.execute.return_value = make_scalar_result(None)
        with pytest.raises(ValueError, match="not_found"):
            await note_service.update_note(mock_session, 999, 10, "Text", None, False)

    @pytest.mark.asyncio
    async def test_update_clears_page_number(self, mock_session, mock_note):
        mock_session.execute.return_value = make_scalar_result(mock_note)
        await note_service.update_note(mock_session, 1, 10, "Text", None, False)
        assert mock_note.page_number is None


class TestDeleteNote:
    @pytest.mark.asyncio
    async def test_delete_success(self, mock_session):
        returning_result = MagicMock()
        returning_result.scalar_one_or_none.return_value = 1
        mock_session.execute.return_value = returning_result
        await note_service.delete_note(mock_session, 1, 10)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, mock_session):
        returning_result = MagicMock()
        returning_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = returning_result
        with pytest.raises(ValueError, match="not_found"):
            await note_service.delete_note(mock_session, 999, 10)


class TestGetBookNotes:
    @pytest.mark.asyncio
    async def test_returns_items_and_count(self, mock_session, mock_note):
        count_result, items_result = make_list_result([mock_note], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await note_service.get_book_notes(
            mock_session, 10, 100, 10, 0, "page_number", "asc"
        )
        assert total == 1
        assert rows == [mock_note]

    @pytest.mark.asyncio
    async def test_sort_by_created_at(self, mock_session, mock_note):
        count_result, items_result = make_list_result([mock_note], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await note_service.get_book_notes(
            mock_session, 10, 100, 10, 0, "created_at", "desc"
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_page_number_desc_sort(self, mock_session, mock_note):
        count_result, items_result = make_list_result([mock_note], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await note_service.get_book_notes(
            mock_session, 10, 100, 10, 0, "page_number", "desc"
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        count_result, items_result = make_list_result([], 0)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await note_service.get_book_notes(
            mock_session, 10, 100, 10, 0, "page_number", "asc"
        )
        assert total == 0


class TestGetUserNotes:
    @pytest.mark.asyncio
    async def test_returns_user_notes(self, mock_session, mock_note):
        count_result, items_result = make_list_result([mock_note], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await note_service.get_user_notes(mock_session, 10, 10, 0)
        assert total == 1
        assert rows == [mock_note]

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        count_result, items_result = make_list_result([], 0)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await note_service.get_user_notes(mock_session, 10, 10, 0)
        assert total == 0
        assert rows == []
