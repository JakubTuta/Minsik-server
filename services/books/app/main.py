import asyncio
import datetime
import logging
import signal
import sys
import typing

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
from app.services.category_service import category_service
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
category_cache_task: asyncio.Task = None
shutdown_event = asyncio.Event()

ES_LAST_SYNC_KEY = "es:last_sync_ts"
ES_LAST_SYNC_KEY_AUTHORS = "es:last_sync_ts:authors"
ES_LAST_SYNC_KEY_SERIES = "es:last_sync_ts:series"

BAYESIAN_PRIOR_MEAN = 3.0
BAYESIAN_MIN_RATINGS = 10


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


def _compute_bayesian_score(total_ratings: int, combined_avg: float) -> float:
    return (
        total_ratings * combined_avg + BAYESIAN_MIN_RATINGS * BAYESIAN_PRIOR_MEAN
    ) / (total_ratings + BAYESIAN_MIN_RATINGS)


async def reindex_all_to_es(full: bool = False) -> None:
    es = app.es_client.get_es()
    settings = app.config.settings
    epoch = datetime.datetime(1970, 1, 1)

    if full:
        last_sync_books = epoch
        last_sync_authors = epoch
        last_sync_series = epoch
        logger.info("[ES] Starting full reindex")
    else:
        raw_ts = await app.cache.redis_client.get(ES_LAST_SYNC_KEY)
        last_sync_books = (
            datetime.datetime.fromisoformat(raw_ts).replace(tzinfo=None)
            if raw_ts
            else epoch
        )
        raw_ts_authors = await app.cache.redis_client.get(ES_LAST_SYNC_KEY_AUTHORS)
        last_sync_authors = (
            datetime.datetime.fromisoformat(raw_ts_authors).replace(tzinfo=None)
            if raw_ts_authors
            else epoch
        )
        raw_ts_series = await app.cache.redis_client.get(ES_LAST_SYNC_KEY_SERIES)
        last_sync_series = (
            datetime.datetime.fromisoformat(raw_ts_series).replace(tzinfo=None)
            if raw_ts_series
            else epoch
        )
        logger.info(
            f"[ES] Starting incremental reindex. last_sync books={last_sync_books.isoformat()} "
            f"authors={last_sync_authors.isoformat()} series={last_sync_series.isoformat()}"
        )

    books_indexed = 0
    authors_indexed = 0
    series_indexed = 0

    async with app.db.async_session_maker() as session:
        books_query = sqlalchemy.text(
            """
            SELECT
                b.book_id, b.title, b.language, b.slug,
                b.primary_cover_url,
                b.rating_count AS app_rating_count, b.avg_rating AS app_avg_rating,
                b.ol_rating_count, b.ol_avg_rating,
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

        result = await session.stream(books_query, {"last_sync": last_sync_books})
        batch: list = []

        async for row in result:
            app_rating_count = row.app_rating_count or 0
            ol_rating_count = row.ol_rating_count or 0
            app_avg = float(row.app_avg_rating) if row.app_avg_rating else 0.0
            ol_avg = float(row.ol_avg_rating) if row.ol_avg_rating else 0.0
            total_ratings = app_rating_count + ol_rating_count
            combined_avg = (
                (app_avg * app_rating_count + ol_avg * ol_rating_count) / total_ratings
                if total_ratings > 0
                else 0.0
            )
            doc = {
                "_index": settings.es_index_books,
                "_id": str(row.book_id),
                "_source": {
                    "book_id": row.book_id,
                    "title": row.title or "",
                    "language": row.language or "",
                    "slug": row.slug or "",
                    "primary_cover_url": row.primary_cover_url or "",
                    "authors_names": list(row.authors_names or []),
                    "author_slugs": list(row.author_slugs or []),
                    "series_name": row.series_name or "",
                    "series_slug": row.series_slug or "",
                    "app_avg_rating": app_avg if app_rating_count > 0 else None,
                    "app_rating_count": app_rating_count,
                    "ol_avg_rating": ol_avg if ol_rating_count > 0 else None,
                    "ol_rating_count": ol_rating_count,
                    "bayesian_score": _compute_bayesian_score(
                        total_ratings, combined_avg
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
                a.author_id, a.name, a.slug, a.photo_url,
                b.language,
                COUNT(DISTINCT b.book_id) as book_count,
                COALESCE(SUM(b.rating_count), 0) as app_rating_count,
                CASE WHEN SUM(b.rating_count) > 0
                     THEN SUM(b.avg_rating * b.rating_count) / SUM(b.rating_count)
                     ELSE NULL END as app_avg_rating,
                COALESCE(SUM(b.ol_rating_count), 0) as ol_rating_count,
                CASE WHEN SUM(b.ol_rating_count) > 0
                     THEN SUM(b.ol_avg_rating * b.ol_rating_count) / SUM(b.ol_rating_count)
                     ELSE NULL END as ol_avg_rating
            FROM books.authors a
            JOIN books.book_authors ba ON a.author_id = ba.author_id
            JOIN books.books b ON ba.book_id = b.book_id
            WHERE a.updated_at > :last_sync AND b.language IS NOT NULL
            GROUP BY a.author_id, a.name, a.slug, a.photo_url, b.language
            ORDER BY a.author_id, b.language
        """
        )

        result = await session.stream(authors_query, {"last_sync": last_sync_authors})
        batch = []

        async for row in result:
            app_rating_count = row.app_rating_count or 0
            ol_rating_count = row.ol_rating_count or 0
            app_avg = float(row.app_avg_rating) if row.app_avg_rating else 0.0
            ol_avg = float(row.ol_avg_rating) if row.ol_avg_rating else 0.0
            total_ratings = app_rating_count + ol_rating_count
            combined_avg = (
                (app_avg * app_rating_count + ol_avg * ol_rating_count) / total_ratings
                if total_ratings > 0
                else 0.0
            )
            doc = {
                "_index": settings.es_index_authors,
                "_id": f"{row.author_id}_{row.language}",
                "_source": {
                    "author_id": row.author_id,
                    "language": row.language,
                    "name": row.name or "",
                    "slug": row.slug or "",
                    "photo_url": row.photo_url or "",
                    "book_count": row.book_count or 0,
                    "app_avg_rating": app_avg if app_rating_count > 0 else None,
                    "app_rating_count": app_rating_count,
                    "ol_avg_rating": ol_avg if ol_rating_count > 0 else None,
                    "ol_rating_count": ol_rating_count,
                    "bayesian_score": _compute_bayesian_score(
                        total_ratings, combined_avg
                    ),
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
                s.series_id, s.name, s.slug,
                b.language,
                COUNT(DISTINCT b.book_id) as book_count,
                COALESCE(SUM(b.rating_count), 0) as app_rating_count,
                CASE WHEN SUM(b.rating_count) > 0
                     THEN SUM(b.avg_rating * b.rating_count) / SUM(b.rating_count)
                     ELSE NULL END as app_avg_rating,
                COALESCE(SUM(b.ol_rating_count), 0) as ol_rating_count,
                CASE WHEN SUM(b.ol_rating_count) > 0
                     THEN SUM(b.ol_avg_rating * b.ol_rating_count) / SUM(b.ol_rating_count)
                     ELSE NULL END as ol_avg_rating
            FROM books.series s
            JOIN books.books b ON s.series_id = b.series_id
            WHERE s.updated_at > :last_sync AND b.language IS NOT NULL
            GROUP BY s.series_id, s.name, s.slug, b.language
            ORDER BY s.series_id, b.language
        """
        )

        result = await session.stream(series_query, {"last_sync": last_sync_series})
        batch = []

        async for row in result:
            app_rating_count = row.app_rating_count or 0
            ol_rating_count = row.ol_rating_count or 0
            app_avg = float(row.app_avg_rating) if row.app_avg_rating else 0.0
            ol_avg = float(row.ol_avg_rating) if row.ol_avg_rating else 0.0
            total_ratings = app_rating_count + ol_rating_count
            combined_avg = (
                (app_avg * app_rating_count + ol_avg * ol_rating_count) / total_ratings
                if total_ratings > 0
                else 0.0
            )
            doc = {
                "_index": settings.es_index_series,
                "_id": f"{row.series_id}_{row.language}",
                "_source": {
                    "series_id": row.series_id,
                    "language": row.language,
                    "name": row.name or "",
                    "slug": row.slug or "",
                    "book_count": row.book_count or 0,
                    "app_avg_rating": app_avg if app_rating_count > 0 else None,
                    "app_rating_count": app_rating_count,
                    "ol_avg_rating": ol_avg if ol_rating_count > 0 else None,
                    "ol_rating_count": ol_rating_count,
                    "bayesian_score": _compute_bayesian_score(
                        total_ratings, combined_avg
                    ),
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

    now_ts = datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat()
    await app.cache.redis_client.set(ES_LAST_SYNC_KEY, now_ts)
    await app.cache.redis_client.set(ES_LAST_SYNC_KEY_AUTHORS, now_ts)
    await app.cache.redis_client.set(ES_LAST_SYNC_KEY_SERIES, now_ts)

    logger.info(
        f"[ES] Reindex complete. books={books_indexed}, authors={authors_indexed}, series={series_indexed}"
    )


async def _bulk_index(es: object, docs: list) -> None:
    try:
        await elasticsearch.helpers.async_bulk(es, docs)
    except Exception as e:
        logger.error(f"[ES] Bulk index error: {str(e)}")
        raise


async def _run_initial_reindex() -> None:
    try:
        await reindex_all_to_es(full=True)
    except Exception as e:
        logger.error(
            f"[ES] Initial full reindex failed, service will continue without fresh index: {str(e)}"
        )


async def reindex_periodically() -> None:
    logger.info("Starting ES reindex background task")
    while not shutdown_event.is_set():
        try:
            await reindex_all_to_es(full=False)
        except asyncio.CancelledError:
            logger.info("ES reindex task cancelled")
            break
        except Exception as e:
            logger.error(f"[ES] Reindex error: {str(e)}")
        await asyncio.sleep(app.config.settings.es_reindex_interval_hours * 3600)


async def populate_category_cache_periodically() -> None:
    logger.info("Starting category cache background task")
    while not shutdown_event.is_set():
        try:
            await category_service.populate_category_top_books_cache()
        except asyncio.CancelledError:
            logger.info("Category cache task cancelled")
            break
        except Exception as e:
            logger.error(f"[Category cache] Error: {str(e)}")
        await asyncio.sleep(
            app.config.settings.category_cache_refresh_interval_hours * 3600
        )


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

    logger.info("Initializing Categories")
    await category_service.setup()

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
    category_cache_task = asyncio.create_task(populate_category_cache_periodically())
    asyncio.create_task(_run_initial_reindex())

    logger.info("Books service is running")


async def shutdown() -> None:
    global grpc_server, view_count_flush_task, reindex_task, category_cache_task

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

    if category_cache_task:
        category_cache_task.cancel()
        try:
            await category_cache_task
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
