import asyncio
import logging
import typing

import app.config
import app.db
import app.es_client
import elasticsearch
import elasticsearch.helpers
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

ES_RECONCILE_THROTTLE_SECONDS = 0.2

# Every document keys itself as "<kind>:<identity>", identity being the same
# value the catalog uses elsewhere — work_id, author_id, series slug — so a
# ghost is simply an id whose bare identity Postgres no longer knows, and no
# document source has to be fetched to notice.
_ID_PREFIXES: typing.Dict[str, str] = {"books": "book:", "authors": "author:", "series": "series:"}
_KINDS: typing.Dict[str, str] = {"books": "book", "authors": "author", "series": "series"}
_IDENTITY_QUERIES: typing.Dict[str, str] = {
    "books": "SELECT DISTINCT work_id AS identity FROM books.books WHERE work_id = ANY(:ids)",
    "authors": "SELECT author_id::text AS identity FROM books.authors WHERE author_id::text = ANY(:ids)",
    "series": "SELECT DISTINCT slug AS identity FROM books.series WHERE slug = ANY(:ids)",
}


async def _find_stale_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession, entity: str, doc_ids: typing.List[str]
) -> typing.Set[str]:
    prefix = _ID_PREFIXES[entity]
    bare_ids = [doc_id[len(prefix):] for doc_id in doc_ids]
    result = await session.execute(
        sqlalchemy.text(_IDENTITY_QUERIES[entity]), {"ids": bare_ids}
    )
    present = {row.identity for row in result.fetchall()}

    return {
        doc_id
        for doc_id, bare_id in zip(doc_ids, bare_ids)
        if bare_id not in present
    }


async def _reconcile_index(
    es: elasticsearch.AsyncElasticsearch,
    index: str,
    entity: str,
    batch_size: int,
) -> int:
    total_deleted = 0
    batch: typing.List[str] = []

    async def _flush(current_batch: typing.List[str]) -> int:
        if not current_batch:
            return 0
        try:
            async with app.db.async_session_maker() as session:
                stale_ids = await _find_stale_ids(session, entity, current_batch)
        except Exception as e:
            logger.error(f"[ES] Reconcile PG lookup failed for {index}/{entity}: {e}")
            return 0

        if not stale_ids:
            return 0

        ops = [
            {"_op_type": "delete", "_index": index, "_id": doc_id}
            for doc_id in stale_ids
        ]
        try:
            _, errors = await elasticsearch.helpers.async_bulk(
                es, ops, raise_on_error=False
            )
            return len(ops) - (len(errors) if errors else 0)
        except Exception as e:
            logger.error(f"[ES] Reconcile delete failed for {index}/{entity}: {e}")
            return 0

    try:
        async for hit in elasticsearch.helpers.async_scan(
            es,
            index=index,
            size=batch_size,
            _source=False,
            query={"query": {"term": {"kind": _KINDS[entity]}}},
        ):
            batch.append(hit["_id"])
            if len(batch) >= batch_size:
                total_deleted += await _flush(batch)
                batch = []
                await asyncio.sleep(ES_RECONCILE_THROTTLE_SECONDS)

        total_deleted += await _flush(batch)
    except Exception as e:
        logger.error(f"[ES] Reconcile scan failed for {index}/{entity}: {e}")

    return total_deleted


async def reconcile_deleted_docs() -> typing.Dict[str, int]:
    settings = app.config.settings
    stats = {"books_deleted": 0, "authors_deleted": 0, "series_deleted": 0}

    if not settings.es_reconcile_enabled:
        return stats

    es = app.es_client.get_es()
    batch_size = settings.es_reconcile_scan_size
    index = settings.es_index_catalog

    for entity in ("books", "authors", "series"):
        try:
            stats[f"{entity}_deleted"] = await _reconcile_index(
                es, index, entity, batch_size
            )
        except Exception as e:
            logger.error(f"[ES] Reconcile failed for {entity}: {e}")

    logger.info(
        f"[ES] Reconcile complete. books_deleted={stats['books_deleted']}, "
        f"authors_deleted={stats['authors_deleted']}, series_deleted={stats['series_deleted']}"
    )
    return stats
