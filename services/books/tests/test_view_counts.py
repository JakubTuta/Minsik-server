from unittest.mock import AsyncMock, MagicMock

import app.cache as cache
import pytest


@pytest.fixture
def redis_client(monkeypatch):
    client = MagicMock()
    client.eval = AsyncMock()
    pipeline = MagicMock()
    pipeline.execute = AsyncMock()
    client.pipeline.return_value = pipeline

    async def scan_iter(match, count):
        for key in ("view_count:book:7", "view_count:book:9"):
            yield key

    client.scan_iter = scan_iter
    monkeypatch.setattr(cache, "redis_client", client)
    return client


@pytest.mark.asyncio
async def test_claimed_counters_are_parsed_by_entity_id(redis_client) -> None:
    redis_client.eval.return_value = [
        ["view_count:book:7", "5", "1700000000"],
        ["view_count:book:9", "", ""],
    ]

    claimed = await cache.claim_pending_view_counts("book")

    assert claimed == {7: {"count": 5, "last_viewed": 1700000000}}


@pytest.mark.asyncio
async def test_a_failed_database_write_puts_the_counters_back(redis_client) -> None:
    redis_client.eval.return_value = [["view_count:book:7", "5", "1700000000"]]
    session = AsyncMock()
    session.execute.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await cache.flush_view_counts(session, "book", "books.books", "book_id")

    session.rollback.assert_awaited_once()
    redis_client.pipeline.return_value.hincrby.assert_called_once_with("view_count:book:7", "count", 5)


@pytest.mark.asyncio
async def test_a_successful_flush_does_not_restore_anything(redis_client) -> None:
    redis_client.eval.return_value = [["view_count:book:7", "5", "1700000000"]]
    session = AsyncMock()

    flushed = await cache.flush_view_counts(session, "book", "books.books", "book_id")

    assert flushed == 1
    session.commit.assert_awaited_once()
    redis_client.pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_nothing_pending_writes_nothing(redis_client) -> None:
    redis_client.eval.return_value = []
    session = AsyncMock()

    assert await cache.flush_view_counts(session, "series", "books.series", "series_id") == 0
    session.execute.assert_not_called()
