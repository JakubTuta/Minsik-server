from unittest.mock import AsyncMock, MagicMock

import app.workers.dump.phases.orchestrator as orchestrator
import pytest


@pytest.mark.asyncio
async def test_import_does_not_start_while_another_holds_the_lock(monkeypatch) -> None:
    redis_client = MagicMock()
    redis_client.set.return_value = None
    body = AsyncMock()
    monkeypatch.setattr(orchestrator, "_run_import_dump_locked", body)

    await orchestrator.run_import_dump("job-2", redis_client)

    body.assert_not_awaited()
    redis_client.delete.assert_not_called()
    assert redis_client.set.call_args.kwargs["nx"] is True


@pytest.mark.asyncio
async def test_lock_is_released_when_the_import_fails(monkeypatch) -> None:
    redis_client = MagicMock()
    redis_client.set.return_value = True
    monkeypatch.setattr(
        orchestrator, "_run_import_dump_locked", AsyncMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError):
        await orchestrator.run_import_dump("job-1", redis_client)

    redis_client.delete.assert_called_once_with("dump_import_running")
