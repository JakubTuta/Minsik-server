import asyncio
import signal
import logging
import sys
import grpc
import grpc_health.v1.health
import grpc_health.v1.health_pb2
import grpc_health.v1.health_pb2_grpc
import grpc_reflection.v1alpha.reflection
import app.config
import app.database
import app.cache
import app.grpc.server
import app.proto.user_data_pb2
import app.proto.user_data_pb2_grpc
import app.tracing

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

grpc_server: grpc.aio.Server = None
shutdown_event = asyncio.Event()


# Held so the shutdown task is not garbage collected mid-flight: the loop
# keeps only a weak reference to a task.
_background_tasks: set = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def start_server() -> None:
    global grpc_server

    logger.info("Initializing database connection")
    await app.database.init_db()

    logger.info("Initializing Redis connection")
    await app.cache.init_redis()

    app.tracing.init_ledger()
    grpc_server = grpc.aio.server(interceptors=app.tracing.get_server_interceptors())

    app.proto.user_data_pb2_grpc.add_UserDataServiceServicer_to_server(
        app.grpc.server.UserDataServicer(),
        grpc_server
    )

    health_servicer = grpc_health.v1.health.aio.HealthServicer()
    grpc_health.v1.health_pb2_grpc.add_HealthServicer_to_server(health_servicer, grpc_server)

    SERVICE_NAMES = (
        app.proto.user_data_pb2.DESCRIPTOR.services_by_name['UserDataService'].full_name,
        grpc_health.v1.health.SERVICE_NAME,
        grpc_reflection.v1alpha.reflection.SERVICE_NAME,
    )
    grpc_reflection.v1alpha.reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    grpc_server.add_insecure_port(app.config.settings.listen_address)

    logger.info(f"Starting gRPC server on {app.config.settings.listen_address}")
    await grpc_server.start()

    await health_servicer.set(
        "", grpc_health.v1.health_pb2.HealthCheckResponse.SERVING
    )

    logger.info("User data service is running")


async def shutdown() -> None:
    logger.info("Shutting down User data service")

    shutdown_event.set()

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    logger.info("Closing Redis connection")
    await app.cache.close_redis()

    logger.info("Closing database connection")
    await app.database.close_db()

    await app.tracing.shutdown()

    logger.info("User data service stopped")


def handle_signal(signum, frame) -> None:
    logger.info(f"Received signal {signum}")
    _spawn_background(shutdown())


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
