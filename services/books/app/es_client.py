import typing
import logging
import asyncio
import elasticsearch
import elasticsearch.helpers

logger = logging.getLogger(__name__)

_es_client: typing.Optional[elasticsearch.AsyncElasticsearch] = None

BOOKS_INDEX_MAPPING: typing.Dict[str, typing.Any] = {
    "settings": {
        "analysis": {
            "analyzer": {
                "book_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding", "english_stemmer"]
                }
            },
            "filter": {
                "english_stemmer": {"type": "stemmer", "language": "english"}
            }
        }
    },
    "mappings": {
        "properties": {
            "book_id":           {"type": "long"},
            "title":             {"type": "text", "analyzer": "book_analyzer"},
            "description":       {"type": "text", "analyzer": "book_analyzer"},
            "language":          {"type": "keyword"},
            "slug":              {"type": "keyword"},
            "primary_cover_url": {"type": "keyword", "index": False},
            "authors_names":     {"type": "text", "analyzer": "book_analyzer"},
            "author_slugs":      {"type": "keyword"},
            "series_name":       {"type": "text", "analyzer": "book_analyzer"},
            "series_slug":       {"type": "keyword"},
            "view_count":        {"type": "integer"},
            "last_viewed_at":    {"type": "date"},
            "rating_count":      {"type": "integer"},
            "avg_rating":        {"type": "float"},
            "created_at":        {"type": "date"},
        }
    }
}

AUTHORS_INDEX_MAPPING: typing.Dict[str, typing.Any] = {
    "mappings": {
        "properties": {
            "author_id":      {"type": "long"},
            "name":           {"type": "text", "analyzer": "standard"},
            "bio":            {"type": "text", "analyzer": "standard"},
            "slug":           {"type": "keyword"},
            "photo_url":      {"type": "keyword", "index": False},
            "view_count":     {"type": "integer"},
            "last_viewed_at": {"type": "date"},
            "created_at":     {"type": "date"},
        }
    }
}

SERIES_INDEX_MAPPING: typing.Dict[str, typing.Any] = {
    "mappings": {
        "properties": {
            "series_id":      {"type": "long"},
            "name":           {"type": "text", "analyzer": "standard"},
            "description":    {"type": "text", "analyzer": "standard"},
            "slug":           {"type": "keyword"},
            "view_count":     {"type": "integer"},
            "last_viewed_at": {"type": "date"},
            "created_at":     {"type": "date"},
        }
    }
}


async def init_es(host: str, port: int, max_retries: int = 10) -> None:
    global _es_client
    es_url = f"http://{host}:{port}"
    _es_client = elasticsearch.AsyncElasticsearch([es_url])

    # Retry connection with exponential backoff
    for attempt in range(max_retries):
        try:
            health = await _es_client.cluster.health()
            logger.info(f"Elasticsearch connected: {host}:{port}, cluster status: {health.get('status')}")
            logger.info(f"Elasticsearch client initialized: {host}:{port}")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30 seconds
                logger.warning(f"Elasticsearch connection attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Elasticsearch connection failed after {max_retries} attempts: {e}")
                raise


async def create_indexes(index_books: str, index_authors: str, index_series: str) -> None:
    try:
        # Check and create books index
        try:
            exists = await _es_client.indices.exists(index=index_books)
            if not exists:
                await _es_client.indices.create(index=index_books, body=BOOKS_INDEX_MAPPING)
                logger.info(f"[ES] Created index: {index_books}")
            else:
                logger.info(f"[ES] Index already exists: {index_books}")
        except Exception as e:
            logger.error(f"[ES] Error creating books index: {e}")
            raise

        # Check and create authors index
        try:
            exists = await _es_client.indices.exists(index=index_authors)
            if not exists:
                await _es_client.indices.create(index=index_authors, body=AUTHORS_INDEX_MAPPING)
                logger.info(f"[ES] Created index: {index_authors}")
            else:
                logger.info(f"[ES] Index already exists: {index_authors}")
        except Exception as e:
            logger.error(f"[ES] Error creating authors index: {e}")
            raise

        # Check and create series index
        try:
            exists = await _es_client.indices.exists(index=index_series)
            if not exists:
                await _es_client.indices.create(index=index_series, body=SERIES_INDEX_MAPPING)
                logger.info(f"[ES] Created index: {index_series}")
            else:
                logger.info(f"[ES] Index already exists: {index_series}")
        except Exception as e:
            logger.error(f"[ES] Error creating series index: {e}")
            raise
    except Exception as e:
        logger.error(f"[ES] Failed to create indexes: {e}")
        raise


async def close_es() -> None:
    if _es_client:
        await _es_client.close()
        logger.info("Elasticsearch client closed")


def get_es() -> elasticsearch.AsyncElasticsearch:
    return _es_client
