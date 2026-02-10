import asyncio
import signal
import logging
import sys
import grpc
from grpc_reflection.v1alpha import reflection
import app.config
import app.database
import app.grpc.server
import app.proto.auth_pb2
import app.proto.auth_pb2_grpc

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

grpc_server: grpc.aio.Server = None
shutdown_event = asyncio.Event()


async def start_server() -> None:
    global grpc_server

    logger.info("Initializing database connection")
    await app.database.init_db()

    grpc_server = grpc.aio.server()

    app.proto.auth_pb2_grpc.add_AuthServiceServicer_to_server(
        app.grpc.server.AuthServicer(),
        grpc_server
    )

    SERVICE_NAMES = (
        app.proto.auth_pb2.DESCRIPTOR.services_by_name['AuthService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    grpc_server.add_insecure_port(app.config.settings.listen_address)

    logger.info(f"Starting gRPC server on {app.config.settings.listen_address}")
    await grpc_server.start()

    logger.info("Auth service is running")


async def shutdown() -> None:
    global grpc_server

    logger.info("Shutting down Auth service")

    shutdown_event.set()

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    logger.info("Closing database connection")
    await app.database.close_db()

    logger.info("Auth service stopped")


def handle_signal(signum, frame) -> None:
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
