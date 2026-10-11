import asyncio
from unittest.mock import AsyncMock, MagicMock

import app.cache as cache
import app.services.admin_refresh as admin_refresh
import pytest


@pytest.fixture
def redis_client(monkeypatch):
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock()
    monkeypatch.setattr(cache, "redis_client", client)
    return client


async def _drain() -> None:
    await asyncio.gather(*admin_refresh._running)


@pytest.mark.asyncio
async def test_a_second_refresh_of_the_same_kind_is_refused(redis_client) -> None:
    redis_client.set.return_value = None
    job = AsyncMock()

    assert await admin_refresh.start("home", job) is False

    job.assert_not_awaited()
    assert redis_client.set.call_args.kwargs["nx"] is True


@pytest.mark.asyncio
async def test_job_runs_in_the_background_then_cleans_up_and_releases_the_lock(redis_client) -> None:
    order = []

    async def job() -> None:
        order.append("job")

    async def on_success() -> None:
        order.append("cleanup")

    assert await admin_refresh.start("contextual", job, on_success) is True
    await _drain()

    assert order == ["job", "cleanup"]
    redis_client.delete.assert_awaited_once_with("rec:refresh:running:contextual")


@pytest.mark.asyncio
async def test_failed_job_keeps_the_old_data_and_still_releases_the_lock(redis_client) -> None:
    cleanup = AsyncMock()

    assert await admin_refresh.start("personal", AsyncMock(side_effect=RuntimeError("db down")), cleanup) is True
    await _drain()

    cleanup.assert_not_awaited()
    redis_client.delete.assert_awaited_once_with("rec:refresh:running:personal")
