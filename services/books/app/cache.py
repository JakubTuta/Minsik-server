import json
import logging
import time
import typing

import app.config
import redis.asyncio
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)


redis_client: redis.asyncio.Redis = None


async def init_redis() -> None:
    global redis_client

    redis_client = redis.asyncio.from_url(
        app.config.settings.redis_url,
        max_connections=app.config.settings.redis_max_connections,
        decode_responses=True
    )

    try:
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Redis connection failed: {str(e)}")
        raise


async def close_redis() -> None:
    global redis_client
    if redis_client:
        await redis_client.aclose()


async def get_cached(key: str) -> typing.Optional[typing.Any]:
    try:
        value = await redis_client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        logger.error(f"Redis GET error for key {key}: {str(e)}")
        return None


async def set_cached(key: str, value: typing.Any, ttl: int) -> bool:
    try:
        await redis_client.setex(
            key,
            ttl,
            json.dumps(value)
        )
        return True
    except Exception as e:
        logger.error(f"Redis SET error for key {key}: {str(e)}")
        return False


async def delete_by_pattern(pattern: str) -> int:
    try:
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                await redis_client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted
    except Exception as e:
        logger.error(f"Redis DELETE pattern error for {pattern}: {str(e)}")
        return 0


async def delete_localized(prefix: str, slug: str) -> int:
    """Drop every per-language entry cached under `{prefix}:{slug}:{language}`.

    Detail caches are keyed by the language the reader *asked for*, not by the
    language of the row that was served: a request for a language with no
    edition falls back to another edition and caches it under the requested
    language. Invalidating one language therefore leaves the entries readers
    actually hit stale until the TTL expires, which is why every one of these
    invalidations has to be a pattern delete.
    """
    return await delete_by_pattern(f"{prefix}:{slug}:*")


async def increment_view_count(entity_type: str, entity_id: int) -> None:
    try:
        key = f"view_count:{entity_type}:{entity_id}"
        await redis_client.hincrby(key, "count", 1)
        await redis_client.hset(key, "last_viewed", int(time.time()))
    except Exception as e:
        logger.error(f"Redis view count increment error: {str(e)}")


# Reads and deletes buffered counters in one step per batch of keys. A reader that
# fetched the counters and deleted the keys later would drop every view recorded in
# between; claiming them atomically means a view lands either in this flush or the next.
_CLAIM_VIEW_COUNTS_LUA = """
local claimed = {}
for _, key in ipairs(KEYS) do
    local count = redis.call('HGET', key, 'count')
    local last_viewed = redis.call('HGET', key, 'last_viewed')
    redis.call('DEL', key)
    claimed[#claimed + 1] = {key, count or '', last_viewed or ''}
end
return claimed
"""
_CLAIM_BATCH = 500


async def claim_pending_view_counts(entity_type: str) -> typing.Dict[int, typing.Dict[str, int]]:
    """Take every buffered counter of an entity type out of Redis and return it."""
    try:
        keys = [key async for key in redis_client.scan_iter(match=f"view_count:{entity_type}:*", count=1000)]
        claimed: typing.Dict[int, typing.Dict[str, int]] = {}
        for start in range(0, len(keys), _CLAIM_BATCH):
            batch = keys[start:start + _CLAIM_BATCH]
            for key, count, last_viewed in await redis_client.eval(_CLAIM_VIEW_COUNTS_LUA, len(batch), *batch):
                if count and last_viewed:
                    claimed[int(key.split(":")[-1])] = {"count": int(count), "last_viewed": int(last_viewed)}
        return claimed
    except Exception as e:
        logger.error(f"Redis claim view counts error: {str(e)}")
        return {}


async def restore_view_counts(entity_type: str, counts: typing.Dict[int, typing.Dict[str, int]]) -> None:
    """Put claimed counters back after a failed database write, so the views are not lost."""
    try:
        pipeline = redis_client.pipeline()
        for entity_id, data in counts.items():
            key = f"view_count:{entity_type}:{entity_id}"
            pipeline.hincrby(key, "count", data["count"])
            pipeline.hset(key, "last_viewed", data["last_viewed"])
        await pipeline.execute()
    except Exception as e:
        logger.error(f"Redis restore view counts error: {str(e)}")


async def flush_view_counts(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    entity_type: str,
    table: str,
    id_column: str,
) -> int:
    """Apply Redis-buffered view counts to `table`. Returns rows flushed."""
    pending_counts = await claim_pending_view_counts(entity_type)
    if not pending_counts:
        return 0

    # One statement for the whole flush: the buffer holds every entity viewed
    # since the last run, so a statement per entity meant thousands of round
    # trips every few minutes.
    try:
        await session.execute(
            sqlalchemy.text(
                f"""
                UPDATE {table} AS t
                SET
                    view_count = t.view_count + v.increment,
                    last_viewed_at = to_timestamp(v.last_viewed)
                FROM UNNEST(
                    CAST(:entity_ids AS bigint[]),
                    CAST(:increments AS int[]),
                    CAST(:last_viewed AS double precision[])
                ) AS v(entity_id, increment, last_viewed)
                WHERE t.{id_column} = v.entity_id
                """
            ),
            {
                "entity_ids": [int(entity_id) for entity_id in pending_counts],
                "increments": [int(data["count"]) for data in pending_counts.values()],
                "last_viewed": [float(data["last_viewed"]) for data in pending_counts.values()],
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await restore_view_counts(entity_type, pending_counts)
        raise
    return len(pending_counts)
