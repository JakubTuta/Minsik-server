import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


def make_book_row(
    book_id=1,
    title="Test Book",
    slug="test-book",
    language="en",
    primary_cover_url="https://example.com/cover.jpg",
    avg_rating="4.20",
    rating_count=10,
    author_names=None,
    author_slugs=None,
    score=500,
):
    row = MagicMock()
    row.book_id = book_id
    row.title = title
    row.slug = slug
    row.language = language
    row.primary_cover_url = primary_cover_url
    row.avg_rating = avg_rating
    row.rating_count = rating_count
    row.author_names = author_names or ["Author One"]
    row.author_slugs = author_slugs or ["author-one"]
    row.score = score
    return row


def make_author_row(
    author_id=1,
    name="Author One",
    slug="author-one",
    photo_url="https://example.com/photo.jpg",
    book_count=5,
    score=1000,
):
    row = MagicMock()
    row.author_id = author_id
    row.name = name
    row.slug = slug
    row.photo_url = photo_url
    row.book_count = book_count
    row.score = score
    return row


def make_execute_result(rows):
    result = MagicMock()
    result.__iter__ = MagicMock(return_value=iter(rows))
    return result
