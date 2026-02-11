import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_bookshelf():
    row = MagicMock()
    row.bookshelf_id = 1
    row.user_id = 10
    row.book_id = 100
    row.status = "want_to_read"
    row.is_favorite = False
    row.created_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    row.updated_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    return row


@pytest.fixture
def mock_rating():
    row = MagicMock()
    row.rating_id = 1
    row.user_id = 10
    row.book_id = 100
    row.overall_rating = 4.5
    row.review_text = "Great book"
    row.pacing = None
    row.emotional_impact = None
    row.intellectual_depth = None
    row.writing_quality = None
    row.rereadability = None
    row.created_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    row.updated_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    return row


@pytest.fixture
def mock_comment():
    row = MagicMock()
    row.comment_id = 1
    row.user_id = 10
    row.book_id = 100
    row.body = "Really enjoyed this book!"
    row.is_spoiler = False
    row.is_deleted = False
    row.created_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    row.updated_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    return row


@pytest.fixture
def mock_note():
    row = MagicMock()
    row.note_id = 1
    row.user_id = 10
    row.book_id = 100
    row.note_text = "Remember this passage"
    row.page_number = 42
    row.is_spoiler = False
    row.created_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    row.updated_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    return row


def make_scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    result.scalars.return_value.all.return_value = value if isinstance(value, list) else []
    return result


def make_list_result(items, count):
    count_result = MagicMock()
    count_result.scalar_one.return_value = count

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = items

    return count_result, items_result
