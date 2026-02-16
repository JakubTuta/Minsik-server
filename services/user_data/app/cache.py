import redis.asyncio
import logging
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
        await redis_client.delete(f"book_slug:{book_slug}")
    except Exception as e:
        logger.error(f"Redis DELETE error for book_slug:{book_slug}: {str(e)}")
