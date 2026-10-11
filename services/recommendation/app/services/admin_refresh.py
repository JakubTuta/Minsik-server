import asyncio
import logging
import typing

import app.cache

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "rec:refresh:running:"
_LOCK_TTL_SECONDS = 4 * 3600

# The event loop keeps only a weak reference to a task, so a fire-and-forget refresh
# could be collected while suspended and silently never finish.
_running: typing.Set[asyncio.Task] = set()


async def start(
    name: str,
    job: typing.Callable[[], typing.Awaitable[None]],
    on_success: typing.Optional[typing.Callable[[], typing.Awaitable[typing.Any]]] = None,
) -> bool:
    """Run an admin-triggered rebuild past the request; False when one of that name is already running.

    A rebuild takes minutes, longer than the gateway waits. Running it inside the request meant
    a client timeout cancelled it halfway, after the old data had already been deleted. Here the
    job overwrites live keys as it goes and `on_success` only clears what a finished rebuild
    left stale, so readers never see an emptied cache.
    """
    claimed = await app.cache.redis_client.set(
        f"{_LOCK_PREFIX}{name}", "1", nx=True, ex=_LOCK_TTL_SECONDS
    )
    if not claimed:
        return False

    async def run() -> None:
        try:
            await job()
            if on_success is not None:
                await on_success()
        except Exception:
            logger.exception(f"[rec:admin] Refresh '{name}' failed")
        finally:
            try:
                await app.cache.redis_client.delete(f"{_LOCK_PREFIX}{name}")
            except Exception:
                logger.exception(f"[rec:admin] Could not release the '{name}' refresh lock")

    task = asyncio.create_task(run())
    _running.add(task)
    task.add_done_callback(_running.discard)
    return True
