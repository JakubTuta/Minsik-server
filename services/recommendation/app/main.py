import asyncio
import logging
import signal
import sys

import app.cache
import app.config
import app.db
import app.grpc.server
import app.proto.recommendation_pb2
import app.proto.recommendation_pb2_grpc
import app.services.case_pool_builder
import app.services.contextual_precompute
import app.services.list_builder
import app.services.personal_refresher
import grpc
from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from grpc_reflection.v1alpha import reflection

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

grpc_server: grpc.aio.Server = None
scheduler: AsyncScheduler = None


async def _midnight_refresh() -> None:
    logger.info("[rec] Running midnight recommendation refresh")
    try:
        await app.services.list_builder.refresh_all(app.db.async_session_maker)
        logger.info("[rec] Midnight refresh complete")
    except Exception as e:
        logger.error(f"[rec] Midnight refresh error: {str(e)}")


async def _personal_refresh() -> None:
    logger.info("[rec:personal] Running 1AM personalized recommendation refresh")
    try:
        await app.services.personal_refresher.refresh_all_personal(
            app.db.async_session_maker
        )
        logger.info("[rec:personal] 1AM personal refresh complete")
    except Exception as e:
        logger.error(f"[rec:personal] 1AM personal refresh error: {str(e)}")


async def _contextual_precompute_refresh() -> None:
    logger.info("[rec:precompute] Running 2AM contextual precompute refresh")
    try:
        await app.services.contextual_precompute.refresh_contextual_recs(
            app.db.async_session_maker
        )
        logger.info("[rec:precompute] 2AM contextual precompute refresh complete")
    except Exception as e:
        logger.error(f"[rec:precompute] 2AM contextual precompute error: {str(e)}")


async def _case_pool_refresh() -> None:
    logger.info("[case] Running case pool refresh")
    try:
        await app.services.case_pool_builder.refresh_case_pools(
            app.db.async_session_maker
        )
        logger.info("[case] Case pool refresh complete")
    except Exception as e:
        logger.error(f"[case] Case pool refresh error: {str(e)}")


async def run_initial_jobs() -> None:
    logger.info("Waiting 15 seconds before running initial scheduled jobs...")
    await asyncio.sleep(15)

    logger.info("[rec] Running initial recommendation list refresh at startup")
    try:
        await app.services.list_builder.refresh_all(app.db.async_session_maker)
        logger.info("[rec] Initial list refresh complete")
    except Exception as e:
        logger.error(f"[rec] Initial list refresh failed: {str(e)}")

    logger.info("[rec:personal] Running initial personal refresh at startup")
    try:
        await app.services.personal_refresher.refresh_all_personal(
            app.db.async_session_maker
        )
        logger.info("[rec:personal] Initial personal refresh complete")
    except Exception as e:
        logger.error(f"[rec:personal] Initial personal refresh failed: {str(e)}")

    logger.info("[case] Running initial case pool refresh at startup")
    try:
        await app.services.case_pool_builder.refresh_case_pools(
            app.db.async_session_maker
        )
        logger.info("[case] Initial case pool refresh complete")
    except Exception as e:
        logger.error(f"[case] Initial case pool refresh failed: {str(e)}")


async def start_server() -> None:
    global grpc_server, scheduler

    logger.info("Initializing database connection")
    await app.db.init_db()

    logger.info("Initializing Redis connection")
    await app.cache.init_redis()

    grpc_server = grpc.aio.server()

    app.proto.recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        app.grpc.server.RecommendationServicer(), grpc_server
    )

    SERVICE_NAMES = (
        app.proto.recommendation_pb2.DESCRIPTOR.services_by_name[
            "RecommendationService"
        ].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    listen_addr = f"{app.config.settings.recommendation_service_host}:{app.config.settings.recommendation_grpc_port}"
    grpc_server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()

    asyncio.create_task(run_initial_jobs())

    scheduler = AsyncScheduler()
    await scheduler.__aenter__()
    await scheduler.add_schedule(_midnight_refresh, CronTrigger(hour=0, minute=0))
    await scheduler.add_schedule(_personal_refresh, CronTrigger(hour=1, minute=0))
    await scheduler.add_schedule(_contextual_precompute_refresh, CronTrigger(hour=2, minute=0))
    await scheduler.add_schedule(_case_pool_refresh, CronTrigger(minute=0))
    await scheduler.start_in_background()
    logger.info("[rec] Midnight refresh scheduled (cron: '0 0 * * *')")
    logger.info("[rec:personal] Personal refresh scheduled (cron: '0 1 * * *')")
    logger.info("[rec:precompute] Contextual precompute scheduled (cron: '0 2 * * *')")
    logger.info("[case] Case pool refresh scheduled (cron: every hour)")

    logger.info("Recommendation service is running")


_shutdown_event: asyncio.Event = None


async def shutdown() -> None:
    global grpc_server, scheduler

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

    logger.info("Recommendation service stopped")


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
