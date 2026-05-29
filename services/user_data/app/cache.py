import json
import redis.asyncio
import logging
import typing
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


async def delete_book_cache(book_slug: str) -> None:
    try:
        pattern = f"book_slug:{book_slug}:*"
        keys = [key async for key in redis_client.scan_iter(match=pattern)]
        if keys:
            await redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis DELETE error for book_slug:{book_slug}:*: {str(e)}")


async def get_json(key: str) -> typing.Optional[typing.Any]:
    try:
        value = await redis_client.get(key)
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.error(f"Redis GET error for {key}: {str(e)}")
        return None


async def set_json(key: str, value: typing.Any, ttl: int) -> None:
    try:
        await redis_client.set(key, json.dumps(value), ex=ttl)
    except Exception as e:
        logger.error(f"Redis SET error for {key}: {str(e)}")


async def delete_profile_stats(user_id: int) -> None:
    try:
        await redis_client.delete(f"profile_stats:{user_id}")
    except Exception as e:
        logger.error(f"Redis DELETE error for profile_stats:{user_id}: {str(e)}")


async def delete_profile_overview(user_id: int) -> None:
    try:
        await redis_client.delete(f"profile_overview:{user_id}")
    except Exception as e:
        logger.error(f"Redis DELETE error for profile_overview:{user_id}: {str(e)}")


async def delete_bookshelf_list_cache(user_id: int) -> None:
    try:
        pattern = f"bookshelf_list:{user_id}:*"
        keys = [key async for key in redis_client.scan_iter(match=pattern)]
        if keys:
            await redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis DELETE error for bookshelf_list:{user_id}:*: {str(e)}")


async def delete_comment_list_cache(user_id: int) -> None:
    try:
        pattern = f"comments_list:{user_id}:*"
        keys = [key async for key in redis_client.scan_iter(match=pattern)]
        if keys:
            await redis_client.delete(*keys)
    except Exception as e:
        logger.error(f"Redis DELETE error for comments_list:{user_id}:*: {str(e)}")
