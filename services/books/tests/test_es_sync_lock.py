import datetime
from unittest.mock import AsyncMock, MagicMock

import app.cache as cache
import app.services.es_sync_service as es_sync
import pytest


@pytest.fixture
def redis_client(monkeypatch):
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock()
    monkeypatch.setattr(cache, "redis_client", client)
    return client


@pytest.mark.asyncio
async def test_reindex_is_skipped_while_another_one_holds_the_lock(redis_client, monkeypatch) -> None:
    redis_client.set.return_value = None
    body = AsyncMock()
    monkeypatch.setattr(es_sync, "_reindex_all_to_es_locked", body)

    await es_sync.reindex_all_to_es(full=False)

    body.assert_not_awaited()
    redis_client.delete.assert_not_awaited()
    assert redis_client.set.call_args.kwargs["nx"] is True


@pytest.mark.asyncio
async def test_lock_is_released_when_the_reindex_crashes(redis_client, monkeypatch) -> None:
    monkeypatch.setattr(
        es_sync, "_reindex_all_to_es_locked", AsyncMock(side_effect=RuntimeError("es down"))
    )

    with pytest.raises(RuntimeError):
        await es_sync.reindex_all_to_es(full=True)

    redis_client.delete.assert_awaited_once_with(es_sync.ES_REINDEX_RUNNING_KEY)


@pytest.mark.asyncio
async def test_incremental_sync_rereads_a_window_before_the_watermark(redis_client) -> None:
    watermark = datetime.datetime(2026, 5, 1, 12, 0, 0)
    redis_client.get.return_value = watermark.isoformat()

    assert await es_sync._read_last_sync("k") == watermark - es_sync.ES_INCREMENTAL_OVERLAP


@pytest.mark.asyncio
async def test_a_missing_watermark_means_everything_is_due(redis_client) -> None:
    assert await es_sync._read_last_sync("k") == es_sync.EPOCH
