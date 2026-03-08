import asyncio
import logging
import typing

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
                    "filter": ["lowercase", "asciifolding", "english_stemmer"],
                }
            },
            "filter": {"english_stemmer": {"type": "stemmer", "language": "english"}},
        }
    },
    "mappings": {
        "properties": {
            "book_id": {"type": "long", "index": False},
            "title": {"type": "text", "analyzer": "book_analyzer"},
            "language": {"type": "keyword"},
            "slug": {"type": "keyword"},
            "primary_cover_url": {"type": "keyword", "index": False},
            "authors_names": {"type": "text", "analyzer": "book_analyzer"},
            "author_slugs": {"type": "keyword", "index": False},
            "series_name": {"type": "text", "analyzer": "book_analyzer"},
            "series_slug": {"type": "keyword", "index": False},
            "app_avg_rating": {"type": "float", "index": False},
            "app_rating_count": {"type": "integer", "index": False},
            "ol_avg_rating": {"type": "float", "index": False},
            "ol_rating_count": {"type": "integer", "index": False},
            "bayesian_score": {"type": "float"},
        }
    },
}

AUTHORS_INDEX_MAPPING: typing.Dict[str, typing.Any] = {
    "mappings": {
        "properties": {
            "author_id": {"type": "long", "index": False},
            "language": {"type": "keyword"},
            "name": {"type": "text", "analyzer": "standard"},
            "slug": {"type": "keyword"},
            "photo_url": {"type": "keyword", "index": False},
            "book_count": {"type": "integer", "index": False},
            "app_avg_rating": {"type": "float", "index": False},
            "app_rating_count": {"type": "integer", "index": False},
            "ol_avg_rating": {"type": "float", "index": False},
            "ol_rating_count": {"type": "integer", "index": False},
            "bayesian_score": {"type": "float"},
        }
    }
}

SERIES_INDEX_MAPPING: typing.Dict[str, typing.Any] = {
    "mappings": {
        "properties": {
            "series_id": {"type": "long", "index": False},
            "language": {"type": "keyword"},
            "name": {"type": "text", "analyzer": "standard"},
            "slug": {"type": "keyword"},
            "book_count": {"type": "integer", "index": False},
            "app_avg_rating": {"type": "float", "index": False},
            "app_rating_count": {"type": "integer", "index": False},
            "ol_avg_rating": {"type": "float", "index": False},
            "ol_rating_count": {"type": "integer", "index": False},
            "bayesian_score": {"type": "float"},
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
            logger.info(
                f"Elasticsearch connected: {host}:{port}, cluster status: {health.get('status')}"
            )
            logger.info(f"Elasticsearch client initialized: {host}:{port}")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = min(2**attempt, 30)  # Exponential backoff, max 30 seconds
                logger.warning(
                    f"Elasticsearch connection attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s..."
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    f"Elasticsearch connection failed after {max_retries} attempts: {e}"
                )
                raise


async def create_indexes(
    index_books: str, index_authors: str, index_series: str
) -> None:
    try:
        for index, mapping in [
            (index_books, BOOKS_INDEX_MAPPING),
            (index_authors, AUTHORS_INDEX_MAPPING),
            (index_series, SERIES_INDEX_MAPPING),
        ]:
            try:
                exists = await _es_client.indices.exists(index=index)
                if exists:
                    await _es_client.indices.delete(index=index)
                    logger.info(f"[ES] Deleted existing index: {index}")
                await _es_client.indices.create(index=index, body=mapping)
                logger.info(f"[ES] Created index: {index}")
            except Exception as e:
                logger.error(f"[ES] Error recreating index {index}: {e}")
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
