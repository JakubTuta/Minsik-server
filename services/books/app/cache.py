import json
import logging
import time
import typing

import app.config
import redis.asyncio

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


async def delete_cached(key: str) -> bool:
    try:
        await redis_client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Redis DELETE error for key {key}: {str(e)}")
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


async def get_pending_view_counts(entity_type: str) -> typing.Dict[int, typing.Dict[str, int]]:
    try:
        pattern = f"view_count:{entity_type}:*"
        keys = []
        async for key in redis_client.scan_iter(match=pattern, count=100):
            keys.append(key)

        if not keys:
            return {}

        result = {}
        for key in keys:
            entity_id = int(key.split(":")[-1])
            count = await redis_client.hget(key, "count")
            last_viewed = await redis_client.hget(key, "last_viewed")

            if count and last_viewed:
                result[entity_id] = {
                    "count": int(count),
                    "last_viewed": int(last_viewed)
                }

        return result
    except Exception as e:
        logger.error(f"Redis get pending view counts error: {str(e)}")
        return {}


async def clear_view_counts(entity_type: str, entity_ids: typing.List[int]) -> None:
    try:
        if not entity_ids:
            return

        keys = [f"view_count:{entity_type}:{entity_id}" for entity_id in entity_ids]
        await redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis clear view counts error: {str(e)}")
