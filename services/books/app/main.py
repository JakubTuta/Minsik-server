import asyncio
import signal
import logging
import sys
import grpc
from grpc_reflection.v1alpha import reflection
import app.config
import app.db
import app.cache
import app.grpc.server
import app.proto.books_pb2
import app.proto.books_pb2_grpc
import app.services.book_service
import app.services.author_service

logging.basicConfig(
    level=getattr(logging, app.config.settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


grpc_server: grpc.aio.Server = None
view_count_flush_task: asyncio.Task = None
shutdown_event = asyncio.Event()


async def flush_view_counts_periodically():
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


async def start_server():
    global grpc_server, view_count_flush_task

    logger.info("Initializing database connection")
    await app.db.init_db()

    logger.info("Initializing Redis connection")
    await app.cache.init_redis()

    grpc_server = grpc.aio.server()

    app.proto.books_pb2_grpc.add_BooksServiceServicer_to_server(
        app.grpc.server.BooksServicer(),
        grpc_server
    )

    SERVICE_NAMES = (
        app.proto.books_pb2.DESCRIPTOR.services_by_name['BooksService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, grpc_server)

    listen_addr = f"{app.config.settings.books_service_host}:{app.config.settings.books_grpc_port}"
    grpc_server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await grpc_server.start()

    view_count_flush_task = asyncio.create_task(flush_view_counts_periodically())

    logger.info("Books service is running")


async def shutdown():
    global grpc_server, view_count_flush_task

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

    if grpc_server:
        logger.info("Stopping gRPC server")
        await grpc_server.stop(grace=5)

    logger.info("Closing Redis connection")
    await app.cache.close_redis()

    logger.info("Closing database connection")
    await app.db.close_db()

    logger.info("Books service stopped")


def handle_signal(signum, frame):
    logger.info(f"Received signal {signum}")
    asyncio.create_task(shutdown())


async def main():
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
