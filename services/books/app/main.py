import asyncio
import datetime
import logging
import signal
import sys

import app.cache
import app.config
import app.db
import app.es_client
import app.grpc.server
import app.proto.books_pb2
import app.proto.books_pb2_grpc
import app.services.author_service
import app.services.book_service
import elasticsearch.helpers
import grpc
import sqlalchemy
from grpc_reflection.v1alpha import reflection

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


grpc_server: grpc.aio.Server = None
view_count_flush_task: asyncio.Task = None
reindex_task: asyncio.Task = None
shutdown_event = asyncio.Event()

ES_LAST_SYNC_KEY = "es:last_sync_ts"


async def flush_view_counts_periodically() -> None:
    logger.info("Starting view count flush background task")
    while not shutdown_event.is_set():
        try:
            await asyncio.sleep(app.config.settings.view_count_flush_interval)

            if shutdown_event.is_set():
                break

            async with app.db.async_session_maker() as session:
                await app.services.book_service.flush_view_counts_to_db(session)
                await app.services.author_service.flush_view_counts_to_db(session)
        except asyncio.CancelledError:
            logger.info("View count flush task cancelled")
            break
        except Exception as e:
            logger.error(f"Error flushing view counts: {str(e)}")


async def reindex_all_to_es() -> None:
    es = app.es_client.get_es()
    settings = app.config.settings

    raw_ts = await app.cache.redis_client.get(ES_LAST_SYNC_KEY)
    if raw_ts:
        last_sync = datetime.datetime.fromisoformat(raw_ts)
    else:
        last_sync = datetime.datetime(1970, 1, 1)

    logger.info(f"[ES] Starting reindex. Last sync: {last_sync.isoformat()}")

    books_indexed = 0
    authors_indexed = 0
    series_indexed = 0

    async with app.db.async_session_maker() as session:
        books_query = sqlalchemy.text(
            """
            SELECT
                b.book_id, b.title, b.description, b.language, b.slug,
                b.primary_cover_url, b.view_count, b.last_viewed_at,
                b.rating_count, b.avg_rating, b.created_at,
                ARRAY_AGG(DISTINCT a.name) FILTER (WHERE a.name IS NOT NULL) as authors_names,
                ARRAY_AGG(DISTINCT a.slug) FILTER (WHERE a.slug IS NOT NULL) as author_slugs,
                s.name as series_name, s.slug as series_slug
            FROM books.books b
            LEFT JOIN books.book_authors ba ON b.book_id = ba.book_id
            LEFT JOIN books.authors a ON ba.author_id = a.author_id
            LEFT JOIN books.series s ON b.series_id = s.series_id
            WHERE b.updated_at > :last_sync
            GROUP BY b.book_id, s.name, s.slug
            ORDER BY b.book_id
        """
        )

        result = await session.execute(books_query, {"last_sync": last_sync})
        batch: list = []

        for row in result:
            doc = {
                "_index": settings.es_index_books,
                "_id": str(row.book_id),
                "_source": {
                    "book_id": row.book_id,
                    "title": row.title or "",
                    "description": row.description or "",
                    "language": row.language or "",
                    "slug": row.slug or "",
                    "primary_cover_url": row.primary_cover_url or "",
                    "authors_names": list(row.authors_names or []),
                    "author_slugs": list(row.author_slugs or []),
                    "series_name": row.series_name or "",
                    "series_slug": row.series_slug or "",
                    "view_count": row.view_count or 0,
                    "last_viewed_at": (
                        row.last_viewed_at.isoformat() if row.last_viewed_at else None
                    ),
                    "rating_count": row.rating_count or 0,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                },
            }
            batch.append(doc)

            if len(batch) >= settings.es_reindex_batch_size:
                await _bulk_index(es, batch)
                books_indexed += len(batch)
                batch = []

        if batch:
            await _bulk_index(es, batch)
            books_indexed += len(batch)

        authors_query = sqlalchemy.text(
            """
            SELECT
                a.author_id, a.name, a.bio, a.slug, a.photo_url,
                a.view_count, a.last_viewed_at, a.created_at,
                COUNT(DISTINCT ba.book_id) as book_count,
                COALESCE(AVG(b.avg_rating), 0) as avg_rating,
                COALESCE(SUM(b.rating_count), 0) as rating_count
            FROM books.authors a
            LEFT JOIN books.book_authors ba ON a.author_id = ba.author_id
            LEFT JOIN books.books b ON ba.book_id = b.book_id
            WHERE a.updated_at > :last_sync
            GROUP BY a.author_id
            ORDER BY a.author_id
        """
        )

        result = await session.execute(authors_query, {"last_sync": last_sync})
        batch = []

        for row in result:
            doc = {
                "_index": settings.es_index_authors,
                "_id": str(row.author_id),
                "_source": {
                    "author_id": row.author_id,
                    "name": row.name or "",
                    "bio": row.bio or "",
                    "slug": row.slug or "",
                    "photo_url": row.photo_url or "",
                    "view_count": row.view_count or 0,
                    "last_viewed_at": (
                        row.last_viewed_at.isoformat() if row.last_viewed_at else None
                    ),
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                    "book_count": row.book_count or 0,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                    "rating_count": row.rating_count or 0,
                },
            }
            batch.append(doc)

            if len(batch) >= settings.es_reindex_batch_size:
                await _bulk_index(es, batch)
                authors_indexed += len(batch)
                batch = []

        if batch:
            await _bulk_index(es, batch)
            authors_indexed += len(batch)

        series_query = sqlalchemy.text(
            """
            SELECT
                s.series_id, s.name, s.description, s.slug,
                s.view_count, s.last_viewed_at, s.created_at,
                COUNT(DISTINCT b.book_id) as book_count,
                COALESCE(AVG(b.avg_rating), 0) as avg_rating,
                COALESCE(SUM(b.rating_count), 0) as rating_count
            FROM books.series s
            LEFT JOIN books.books b ON s.series_id = b.series_id
            WHERE s.updated_at > :last_sync
            GROUP BY s.series_id
            ORDER BY s.series_id
        """
        )

        result = await session.execute(series_query, {"last_sync": last_sync})
        batch = []

        for row in result:
            doc = {
                "_index": settings.es_index_series,
                "_id": str(row.series_id),
                "_source": {
                    "series_id": row.series_id,
                    "name": row.name or "",
                    "description": row.description or "",
                    "slug": row.slug or "",
                    "view_count": row.view_count or 0,
                    "last_viewed_at": (
                        row.last_viewed_at.isoformat() if row.last_viewed_at else None
                    ),
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                    "book_count": row.book_count or 0,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else None,
                    "rating_count": row.rating_count or 0,
                },
            }
            batch.append(doc)

            if len(batch) >= settings.es_reindex_batch_size:
                await _bulk_index(es, batch)
                series_indexed += len(batch)
                batch = []

        if batch:
            await _bulk_index(es, batch)
            series_indexed += len(batch)

    now_ts = datetime.datetime.utcnow().isoformat()
    await app.cache.redis_client.set(ES_LAST_SYNC_KEY, now_ts)

    logger.info(
        f"[ES] Reindex complete. books={books_indexed}, authors={authors_indexed}, series={series_indexed}"
    )


async def _bulk_index(es: object, docs: list) -> None:
    try:
        await elasticsearch.helpers.async_bulk(es, docs)
    except Exception as e:
        logger.error(f"[ES] Bulk index error: {str(e)}")


async def reindex_periodically() -> None:
    logger.info("Starting ES reindex background task")
    while not shutdown_event.is_set():
        try:
            await reindex_all_to_es()
        except asyncio.CancelledError:
            logger.info("ES reindex task cancelled")
            break
        except Exception as e:
            logger.error(f"[ES] Reindex error: {str(e)}")
        await asyncio.sleep(app.config.settings.es_reindex_interval_hours * 3600)


async def start_server() -> None:
    global grpc_server, view_count_flush_task, reindex_task

    logger.info("Initializing database connection")
    await app.db.init_db()

    logger.info("Initializing Redis connection")
    await app.cache.init_redis()

    logger.info("Initializing Elasticsearch connection")
    await app.es_client.init_es(
        app.config.settings.es_host, app.config.settings.es_port
    )
    await app.es_client.create_indexes(
        app.config.settings.es_index_books,
        app.config.settings.es_index_authors,
        app.config.settings.es_index_series,
    )

    grpc_server = grpc.aio.server()

    app.proto.books_pb2_grpc.add_BooksServiceServicer_to_server(
        app.grpc.server.BooksServicer(), grpc_server
    )

    SERVICE_NAMES = (
        app.proto.books_pb2.DESCRIPTOR.services_by_name["BooksService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    listen_addr = f"{app.config.settings.books_service_host}:{app.config.settings.books_grpc_port}"
    grpc_server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()

    view_count_flush_task = asyncio.create_task(flush_view_counts_periodically())
    reindex_task = asyncio.create_task(reindex_periodically())

    logger.info("Books service is running")


async def shutdown() -> None:
    global grpc_server, view_count_flush_task, reindex_task

    logger.info("Shutting down Books service")

    shutdown_event.set()

    if view_count_flush_task:
        view_count_flush_task.cancel()
        try:
            await view_count_flush_task
        except asyncio.CancelledError:
            pass

        async with app.db.async_session_maker() as session:
            logger.info("Final flush of view counts")
            await app.services.book_service.flush_view_counts_to_db(session)
            await app.services.author_service.flush_view_counts_to_db(session)

    if reindex_task:
        reindex_task.cancel()
        try:
            await reindex_task
        except asyncio.CancelledError:
            pass

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    logger.info("Closing Elasticsearch connection")
    await app.es_client.close_es()

    logger.info("Closing Redis connection")
    await app.cache.close_redis()

    logger.info("Closing database connection")
    await app.db.close_db()

    logger.info("Books service stopped")


def handle_signal(signum, frame):
    logger.info(f"Received signal {signum}")
    asyncio.create_task(shutdown())


async def main() -> None:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await start_server()
        await grpc_server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
