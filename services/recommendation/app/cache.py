import json
import logging
import typing

import redis.asyncio
import app.config

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


async def flush_recommendation_caches() -> int:
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match="rec:*", count=500)
            if keys:
                await redis_client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        logger.info(f"Flushed {deleted} recommendation cache keys")
    except Exception as e:
        logger.error(f"Redis flush error: {str(e)}")
    return deleted


async def set_cached(key: str, value: typing.Any, ttl: int) -> bool:
    try:
        await redis_client.setex(key, ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.error(f"Redis SET error for key {key}: {str(e)}")
        return False
