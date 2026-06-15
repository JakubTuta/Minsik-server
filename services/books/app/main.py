import asyncio
import logging
import signal
import sys

import app.cache
import app.config
import app.db
import app.es_client
import app.grpc.server
import app.jobs
import app.proto.books_pb2
import app.proto.books_pb2_grpc
import app.tracing
import apscheduler
import apscheduler.triggers.cron
import grpc
import grpc_reflection.v1alpha.reflection

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

grpc_server: grpc.aio.Server = None
scheduler: apscheduler.AsyncScheduler = None
_shutdown_event: asyncio.Event = None


async def start_server() -> None:
    global grpc_server, scheduler

    logger.info("Initializing database connection")
    await app.db.init_db()

    logger.info("Initializing Redis connection")
    await app.cache.init_redis()

    logger.info("Initializing Elasticsearch connection")
    await app.es_client.init_es(
        app.config.settings.es_host, app.config.settings.es_port
    )

    app.tracing.init_ledger()
    grpc_server = grpc.aio.server(interceptors=app.tracing.get_server_interceptors())

    app.proto.books_pb2_grpc.add_BooksServiceServicer_to_server(
        app.grpc.server.BooksServicer(), grpc_server
    )

    SERVICE_NAMES = (
        app.proto.books_pb2.DESCRIPTOR.services_by_name["BooksService"].full_name,
        grpc_reflection.v1alpha.reflection.SERVICE_NAME,
    )
    grpc_reflection.v1alpha.reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    listen_addr = f"{app.config.settings.books_service_host}:{app.config.settings.books_grpc_port}"
    grpc_server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()

    scheduler = apscheduler.AsyncScheduler()
    await scheduler.__aenter__()

    if app.config.settings.view_count_flush_enabled:
        await scheduler.add_schedule(
            app.jobs.flush_view_counts_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.view_count_flush_cron),
        )
        logger.info(
            f"[books] View count flush scheduled (cron: '{app.config.settings.view_count_flush_cron}')"
        )

    if app.config.settings.es_reindex_enabled:
        await scheduler.add_schedule(
            app.jobs.reindex_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.es_reindex_cron),
        )
        logger.info(
            f"[books] ES reindex scheduled (cron: '{app.config.settings.es_reindex_cron}')"
        )

    if app.config.settings.category_cache_refresh_enabled:
        await scheduler.add_schedule(
            app.jobs.category_cache_refresh_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.category_cache_refresh_cron),
        )
        logger.info(
            f"[books] Category cache refresh scheduled (cron: '{app.config.settings.category_cache_refresh_cron}')"
        )
    await scheduler.start_in_background()

    logger.info("Books service is running")


async def shutdown() -> None:
    global grpc_server, scheduler

    logger.info("Shutting down Books service")

    current_scheduler = scheduler
    scheduler = None
    if current_scheduler:
        try:
            await current_scheduler.__aexit__(None, None, None)
        except BaseException:
            pass

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    try:
        logger.info("Final flush of view counts")
        await app.jobs.flush_view_counts_final()
    except Exception as e:
        logger.error(f"Final view count flush failed: {str(e)}")

    logger.info("Closing Elasticsearch connection")
    await app.es_client.close_es()

    logger.info("Closing Redis connection")
    await app.cache.close_redis()

    logger.info("Closing database connection")
    await app.db.close_db()

    await app.tracing.shutdown()

    logger.info("Books service stopped")


def handle_signal(signum, frame):
    global _shutdown_event
    logger.info(f"Received signal {signum}")
    if _shutdown_event and not _shutdown_event.is_set():
        _shutdown_event.set()


async def main() -> None:
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await start_server()
        await _shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
