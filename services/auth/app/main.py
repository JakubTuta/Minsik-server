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
import app.grpc.server
import app.proto.auth_pb2
import app.proto.auth_pb2_grpc
import app.services.auth_service
import app.tracing

TOKEN_PURGE_INTERVAL_SECONDS = 24 * 60 * 60

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

grpc_server: grpc.aio.Server = None
shutdown_event = asyncio.Event()
token_purge_task: asyncio.Task = None


# Held so the shutdown task is not garbage collected mid-flight: the loop
# keeps only a weak reference to a task.
_background_tasks: set = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def run_token_purge_loop() -> None:
    while True:
        try:
            async with app.database.async_session_maker() as session:
                deleted = await app.services.auth_service.purge_stale_refresh_tokens(session)
                if deleted:
                    logger.info(f"Purged {deleted} stale refresh tokens")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Refresh token purge failed: {str(e)}")
        await asyncio.sleep(TOKEN_PURGE_INTERVAL_SECONDS)


async def start_server() -> None:
    global grpc_server

    logger.info("Initializing database connection")
    await app.database.init_db()

    app.tracing.init_ledger()
    grpc_server = grpc.aio.server(interceptors=app.tracing.get_server_interceptors())

    app.proto.auth_pb2_grpc.add_AuthServiceServicer_to_server(
        app.grpc.server.AuthServicer(),
        grpc_server
    )

    health_servicer = grpc_health.v1.health.aio.HealthServicer()
    grpc_health.v1.health_pb2_grpc.add_HealthServicer_to_server(health_servicer, grpc_server)

    SERVICE_NAMES = (
        app.proto.auth_pb2.DESCRIPTOR.services_by_name['AuthService'].full_name,
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

    global token_purge_task
    token_purge_task = asyncio.create_task(run_token_purge_loop())

    logger.info("Auth service is running")


async def shutdown() -> None:
    global grpc_server

    logger.info("Shutting down Auth service")

    shutdown_event.set()

    if token_purge_task:
        token_purge_task.cancel()

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    logger.info("Closing database connection")
    await app.database.close_db()

    await app.tracing.shutdown()

    logger.info("Auth service stopped")


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
