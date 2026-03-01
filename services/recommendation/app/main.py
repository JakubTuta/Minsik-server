import asyncio
import logging
import signal
import sys

import aiocron
import grpc
from grpc_reflection.v1alpha import reflection

import app.cache
import app.config
import app.db
import app.grpc.server
import app.proto.recommendation_pb2
import app.proto.recommendation_pb2_grpc
import app.services.list_builder

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

grpc_server: grpc.aio.Server = None
cron_job: aiocron.Cron = None


async def _midnight_refresh() -> None:
    logger.info("[rec] Running midnight recommendation refresh")
    try:
        async with app.db.async_session_maker() as session:
            await app.services.list_builder.refresh_all(session)
        logger.info("[rec] Midnight refresh complete")
    except Exception as e:
        logger.error(f"[rec] Midnight refresh error: {str(e)}")


async def start_server() -> None:
    global grpc_server, cron_job

    logger.info("Initializing database connection")
    await app.db.init_db()

    logger.info("Initializing Redis connection")
    await app.cache.init_redis()

    grpc_server = grpc.aio.server()

    app.proto.recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        app.grpc.server.RecommendationServicer(), grpc_server
    )

    SERVICE_NAMES = (
        app.proto.recommendation_pb2.DESCRIPTOR.services_by_name["RecommendationService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    listen_addr = f"{app.config.settings.recommendation_service_host}:{app.config.settings.recommendation_grpc_port}"
    grpc_server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()

    logger.info("[rec] Running initial refresh at startup")
    try:
        async with app.db.async_session_maker() as session:
            await app.services.list_builder.refresh_all(session)
    except Exception as e:
        logger.error(f"[rec] Initial refresh error: {str(e)}")

    cron_job = aiocron.crontab("0 0 * * *", func=_midnight_refresh, start=True)
    logger.info("[rec] Midnight refresh scheduled (cron: '0 0 * * *')")

    logger.info("Recommendation service is running")


async def shutdown() -> None:
    global grpc_server, cron_job

    logger.info("Shutting down Recommendation service")

    if cron_job:
        cron_job.stop()

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    logger.info("Closing Redis connection")
    await app.cache.close_redis()

    logger.info("Closing database connection")
    await app.db.close_db()

    logger.info("Recommendation service stopped")


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
