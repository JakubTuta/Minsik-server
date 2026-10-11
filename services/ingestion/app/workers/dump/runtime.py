import asyncio
import ctypes
import logging
import typing

import app.models
import sqlalchemy
import sqlalchemy.exc
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

DEADLOCK_MAX_RETRIES = 3
DEADLOCK_RETRY_DELAY_SECONDS = 2.0


def trim_heap() -> None:
    try:
        ctypes.cdll.LoadLibrary("libc.so.6").malloc_trim(0)
    except OSError:
        pass


async def open_session() -> sqlalchemy.ext.asyncio.AsyncSession:
    session = app.models.AsyncSessionLocal()
    await session.execute(sqlalchemy.text("SET synchronous_commit = off"))
    return session


async def execute_batch(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    statement: sqlalchemy.TextClause,
    params: typing.Union[dict, list[dict]],
) -> None:
    """Run one batch and commit it, retrying the whole batch when Postgres picks it as a deadlock victim.

    Committing per batch bounds what a retry can lose to the batch itself: a
    deadlock aborts the transaction, and rolling back a transaction that spans
    many batches would silently drop the earlier ones.
    """
    for attempt in range(DEADLOCK_MAX_RETRIES + 1):
        try:
            await session.execute(statement, params)
            await session.commit()
            return
        except sqlalchemy.exc.DBAPIError as error:
            await session.rollback()
            if "deadlock" not in str(error).lower() or attempt == DEADLOCK_MAX_RETRIES:
                raise
            logger.warning(f"[dump] Deadlock, retry {attempt + 1}/{DEADLOCK_MAX_RETRIES}")
            await asyncio.sleep(DEADLOCK_RETRY_DELAY_SECONDS * (attempt + 1))
