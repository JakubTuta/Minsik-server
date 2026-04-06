import json
import logging
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
        decode_responses=True,
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
            cursor, keys = await redis_client.scan(
                cursor=cursor, match="rec:*", count=500
            )
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


async def delete_keys(*keys: str) -> int:
    if not keys:
        return 0

    try:
        return int(await redis_client.delete(*keys))
    except Exception as e:
        logger.error(f"Redis DELETE error: {str(e)}")
        return 0


async def delete_by_pattern(pattern: str, scan_count: int = 500) -> int:
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor, match=pattern, count=scan_count
            )
            if keys:
                deleted += int(await redis_client.delete(*keys))
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Redis pattern delete error for {pattern}: {str(e)}")
    return deleted


async def invalidate_user_personal_recommendations(user_id: int) -> int:
    direct_keys = [
        f"rec:profile:{user_id}",
        f"rec:personal:{user_id}",
    ]

    deleted = await delete_keys(*direct_keys)
    deleted += await delete_by_pattern(f"rec:personal:book:{user_id}:*")
    deleted += await delete_by_pattern(f"rec:personal:author:{user_id}:*")

    logger.info(
        "Invalidated personal recommendation cache keys for user_id=%s (deleted=%s)",
        user_id,
        deleted,
    )
    return deleted
