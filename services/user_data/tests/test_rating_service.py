from unittest.mock import MagicMock

import app.services.rating_service as rating_service
import pytest
from tests.conftest import make_list_result, make_scalar_result


class TestUpsertRating:
    @pytest.mark.asyncio
    async def test_upsert_success(self, mock_session, mock_rating):
        mock_session.execute.return_value = make_scalar_result(mock_rating)
        result = await rating_service.upsert_rating(
            mock_session, 10, 100, 4.5, {}, "Great book"
        )
        assert result == mock_rating
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_with_sub_ratings(self, mock_session, mock_rating):
        mock_rating.pacing = 4.0
        mock_rating.writing_quality = 5.0
        mock_session.execute.return_value = make_scalar_result(mock_rating)
        sub_ratings = {"pacing": 4.0, "writing_quality": 5.0}
        result = await rating_service.upsert_rating(
            mock_session, 10, 100, 4.5, sub_ratings, None
        )
        assert result.pacing == 4.0
        assert result.writing_quality == 5.0

    @pytest.mark.asyncio
    async def test_upsert_calls_update_book_stats(self, mock_session, mock_rating):
        mock_session.execute.return_value = make_scalar_result(mock_rating)
        await rating_service.upsert_rating(mock_session, 10, 100, 4.5, {}, None)
        assert mock_session.execute.call_count == 3


class TestDeleteRating:
    @pytest.mark.asyncio
    async def test_delete_success(self, mock_session):
        returning_result = MagicMock()
        returning_result.scalar_one_or_none.return_value = 1
        mock_session.execute.side_effect = [returning_result, MagicMock(), MagicMock()]
        await rating_service.delete_rating(mock_session, 10, 100)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(self, mock_session):
        returning_result = MagicMock()
        returning_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = returning_result
        with pytest.raises(ValueError, match="not_found"):
            await rating_service.delete_rating(mock_session, 10, 999)


class TestGetRating:
    @pytest.mark.asyncio
    async def test_get_success(self, mock_session, mock_rating):
        mock_session.execute.return_value = make_scalar_result(mock_rating)
        result = await rating_service.get_rating(mock_session, 10, 100)
        assert result == mock_rating

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self, mock_session):
        mock_session.execute.return_value = make_scalar_result(None)
        with pytest.raises(ValueError, match="not_found"):
            await rating_service.get_rating(mock_session, 10, 999)


class TestGetUserRatings:
    @pytest.mark.asyncio
    async def test_returns_items_and_count(self, mock_session, mock_rating):
        count_result, items_result = make_list_result([mock_rating], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await rating_service.get_user_ratings(
            mock_session, 10, 10, 0, "created_at", "desc", 0.0, 0.0
        )
        assert total == 1
        assert rows == [mock_rating]

    @pytest.mark.asyncio
    async def test_with_min_rating_filter(self, mock_session, mock_rating):
        count_result, items_result = make_list_result([mock_rating], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await rating_service.get_user_ratings(
            mock_session, 10, 10, 0, "created_at", "desc", 4.0, 0.0
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_max_rating_filter(self, mock_session, mock_rating):
        count_result, items_result = make_list_result([mock_rating], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await rating_service.get_user_ratings(
            mock_session, 10, 10, 0, "created_at", "desc", 0.0, 4.0
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_sort_by_overall_rating(self, mock_session, mock_rating):
        count_result, items_result = make_list_result([mock_rating], 1)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await rating_service.get_user_ratings(
            mock_session, 10, 10, 0, "overall_rating", "asc", 0.0, 0.0
        )
        assert total == 1

    @pytest.mark.asyncio
    async def test_empty_result(self, mock_session):
        count_result, items_result = make_list_result([], 0)
        mock_session.execute.side_effect = [count_result, items_result]
        rows, total = await rating_service.get_user_ratings(
            mock_session, 10, 10, 0, "created_at", "desc", 0.0, 0.0
        )
        assert total == 0
        assert rows == []
