import asyncio
import logging
import signal
import sys

import app.cache
import app.config
import app.db
import app.grpc.server
import app.jobs
import app.proto.recommendation_pb2
import app.proto.recommendation_pb2_grpc
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

    app.tracing.init_ledger()
    grpc_server = grpc.aio.server(interceptors=app.tracing.get_server_interceptors())

    app.proto.recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        app.grpc.server.RecommendationServicer(), grpc_server
    )

    SERVICE_NAMES = (
        app.proto.recommendation_pb2.DESCRIPTOR.services_by_name[
            "RecommendationService"
        ].full_name,
        grpc_reflection.v1alpha.reflection.SERVICE_NAME,
    )
    grpc_reflection.v1alpha.reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    listen_addr = f"{app.config.settings.recommendation_service_host}:{app.config.settings.recommendation_grpc_port}"
    grpc_server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()

    scheduler = apscheduler.AsyncScheduler()
    await scheduler.__aenter__()

    if app.config.settings.general_refresh_enabled:
        await scheduler.add_schedule(
            app.jobs.general_refresh_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.general_refresh_cron),
        )
        logger.info(
            f"[rec] General refresh scheduled (cron: '{app.config.settings.general_refresh_cron}')"
        )

    if app.config.settings.personal_refresh_enabled:
        await scheduler.add_schedule(
            app.jobs.personal_refresh_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.personal_refresh_cron),
        )
        logger.info(
            f"[rec:personal] Personal refresh scheduled (cron: '{app.config.settings.personal_refresh_cron}')"
        )

    if app.config.settings.contextual_precompute_enabled:
        await scheduler.add_schedule(
            app.jobs.contextual_precompute_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.contextual_precompute_cron),
        )
        logger.info(
            f"[rec:precompute] Contextual precompute scheduled (cron: '{app.config.settings.contextual_precompute_cron}')"
        )

    if app.config.settings.case_pool_refresh_enabled:
        await scheduler.add_schedule(
            app.jobs.case_pool_refresh_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.case_pool_refresh_cron),
        )
        logger.info(
            f"[rec:case] Case pool refresh scheduled (cron: '{app.config.settings.case_pool_refresh_cron}')"
        )

    if app.config.settings.book_of_week_enabled:
        await scheduler.add_schedule(
            app.jobs.book_of_week_job,
            apscheduler.triggers.cron.CronTrigger.from_crontab(app.config.settings.book_of_week_cron),
        )
        logger.info(
            f"[rec:bow] Book of the week scheduled (cron: '{app.config.settings.book_of_week_cron}')"
        )

    await scheduler.start_in_background()

    logger.info("Recommendation service is running")


async def shutdown() -> None:
    global scheduler

    logger.info("Shutting down Recommendation service")

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

    logger.info("Closing Redis connection")
    await app.cache.close_redis()

    logger.info("Closing database connection")
    await app.db.close_db()

    await app.tracing.shutdown()

    logger.info("Recommendation service stopped")


def handle_signal(signum, frame):
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
