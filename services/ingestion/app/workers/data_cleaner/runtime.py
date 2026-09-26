import asyncio
import logging
import typing

import app.config
import redis
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

SessionFactory = sqlalchemy.ext.asyncio.async_sessionmaker
StopCheck = typing.Callable[[], bool]
BatchStep = typing.Callable[
    [sqlalchemy.ext.asyncio.AsyncSession],
    typing.Awaitable[typing.Tuple[int, bool]],
]

DUMP_RUNNING_KEY = "dump_import_running"

_DUMP_WAIT_INTERVAL = 30
_MAX_CONSECUTIVE_FAILURES = 3
_FAILURE_BACKOFF_SECONDS = 5
_BATCH_PAUSE_SECONDS = 0.5


def never_stop() -> bool:
    return False


def create_redis_client() -> redis.Redis:
    return redis.Redis(
        host=app.config.settings.redis_host,
        port=app.config.settings.redis_port,
        db=app.config.settings.redis_db,
        password=app.config.settings.redis_password or None,
        decode_responses=True,
    )


async def wait_for_dump_import(stop_check: StopCheck) -> None:
    if not stop_check():
        return
    logger.info("[cleanup] Dump import in progress: pausing cleanup until it completes")
    while stop_check():
        await asyncio.sleep(_DUMP_WAIT_INTERVAL)
    logger.info("[cleanup] Dump import finished: resuming cleanup")


async def run_batches(
    session_factory: SessionFactory,
    label: str,
    step: BatchStep,
    stop_check: StopCheck,
) -> int:
    total = 0
    consecutive_failures = 0

    while True:
        await wait_for_dump_import(stop_check)

        try:
            async with session_factory() as session:
                changed, has_more = await step(session)
                await session.commit()
        except Exception as e:
            consecutive_failures += 1
            logger.error(
                f"[cleanup] {label} batch failed "
                f"({consecutive_failures}/{_MAX_CONSECUTIVE_FAILURES}): {e}"
            )
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                break
            await asyncio.sleep(_FAILURE_BACKOFF_SECONDS)
            continue

        consecutive_failures = 0
        total += changed

        if not has_more:
            break
        await asyncio.sleep(_BATCH_PAUSE_SECONDS)

    if total:
        logger.info(f"[cleanup] {label}: {total} rows affected")
    return total
