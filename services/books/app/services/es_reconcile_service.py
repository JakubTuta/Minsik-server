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

StaleIdFinder = typing.Callable[
    [sqlalchemy.ext.asyncio.AsyncSession, list],
    typing.Awaitable[typing.Set[str]],
]


async def _find_stale_book_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession, hits: list
) -> typing.Set[str]:
    book_ids = [int(hit["_id"]) for hit in hits]
    result = await session.execute(
        sqlalchemy.text("SELECT book_id FROM books.books WHERE book_id = ANY(:ids)"),
        {"ids": book_ids},
    )
    present = {row[0] for row in result.fetchall()}
    return {hit["_id"] for hit in hits if int(hit["_id"]) not in present}


async def _find_stale_author_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession, hits: list
) -> typing.Set[str]:
    author_ids = list({hit["_source"]["author_id"] for hit in hits})
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT ba.author_id, b.language
            FROM books.book_authors ba
            JOIN books.books b ON ba.book_id = b.book_id
            WHERE ba.author_id = ANY(:author_ids)
            """
        ),
        {"author_ids": author_ids},
    )
    present = {(row[0], row[1]) for row in result.fetchall()}
    return {
        hit["_id"]
        for hit in hits
        if (hit["_source"]["author_id"], hit["_source"]["language"]) not in present
    }


async def _find_stale_series_ids(
    session: sqlalchemy.ext.asyncio.AsyncSession, hits: list
) -> typing.Set[str]:
    series_ids = list({hit["_source"]["series_id"] for hit in hits})
    result = await session.execute(
        sqlalchemy.text(
            """
            SELECT DISTINCT b.series_id, b.language
            FROM books.books b
            WHERE b.series_id = ANY(:series_ids)
            """
        ),
        {"series_ids": series_ids},
    )
    present = {(row[0], row[1]) for row in result.fetchall()}
    return {
        hit["_id"]
        for hit in hits
        if (hit["_source"]["series_id"], hit["_source"]["language"]) not in present
    }


async def _reconcile_index(
    es: elasticsearch.AsyncElasticsearch,
    index: str,
    source_fields: typing.Union[bool, list],
    stale_id_finder: StaleIdFinder,
    batch_size: int,
) -> int:
    total_deleted = 0
    batch: list = []

    async def _flush(current_batch: list) -> int:
        if not current_batch:
            return 0
        try:
            async with app.db.async_session_maker() as session:
                stale_ids = await stale_id_finder(session, current_batch)
        except Exception as e:
            logger.error(f"[ES] Reconcile PG lookup failed for {index}: {e}")
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
            logger.error(f"[ES] Reconcile delete failed for {index}: {e}")
            return 0

    try:
        async for hit in elasticsearch.helpers.async_scan(
            es, index=index, size=batch_size, _source=source_fields
        ):
            batch.append(hit)
            if len(batch) >= batch_size:
                total_deleted += await _flush(batch)
                batch = []
                await asyncio.sleep(ES_RECONCILE_THROTTLE_SECONDS)

        total_deleted += await _flush(batch)
    except Exception as e:
        logger.error(f"[ES] Reconcile scan failed for {index}: {e}")

    return total_deleted


async def reconcile_deleted_docs() -> typing.Dict[str, int]:
    settings = app.config.settings
    stats = {"books_deleted": 0, "authors_deleted": 0, "series_deleted": 0}

    if not settings.es_reconcile_enabled:
        return stats

    es = app.es_client.get_es()
    batch_size = settings.es_reconcile_scan_size

    try:
        stats["books_deleted"] = await _reconcile_index(
            es, settings.es_index_books, False, _find_stale_book_ids, batch_size
        )
        stats["authors_deleted"] = await _reconcile_index(
            es,
            settings.es_index_authors,
            ["author_id", "language"],
            _find_stale_author_ids,
            batch_size,
        )
        stats["series_deleted"] = await _reconcile_index(
            es,
            settings.es_index_series,
            ["series_id", "language"],
            _find_stale_series_ids,
            batch_size,
        )
    except Exception as e:
        logger.error(f"[ES] Reconcile failed: {e}")

    logger.info(
        f"[ES] Reconcile complete. books_deleted={stats['books_deleted']}, "
        f"authors_deleted={stats['authors_deleted']}, series_deleted={stats['series_deleted']}"
    )
    return stats
