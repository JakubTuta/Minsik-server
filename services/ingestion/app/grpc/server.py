import asyncio
import concurrent.futures
import json
import logging

import app.config
import app.models
import app.proto.ingestion_pb2 as ingestion_pb2
import app.proto.ingestion_pb2_grpc as ingestion_pb2_grpc
import app.tracing
import app.workers.data_cleaner
import app.workers.dump
import grpc
import redis
import sqlalchemy
import sqlalchemy.ext.asyncio

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
    host=app.config.settings.redis_host,
    port=app.config.settings.redis_port,
    db=app.config.settings.redis_db,
    password=(
        app.config.settings.redis_password
        if app.config.settings.redis_password
        else None
    ),
    decode_responses=True,
)

_COVERAGE_CACHE_KEY = "coverage_stats"
_COVERAGE_CACHE_TTL = 3600
_CLEANUP_RUNNING_KEY = "cleanup_running"


class IngestionService(ingestion_pb2_grpc.IngestionServiceServicer):
    async def GetDataCoverage(self, request, context):
        try:
            cached = redis_client.get(_COVERAGE_CACHE_KEY)
            if cached:
                data = json.loads(cached)
                return ingestion_pb2.GetDataCoverageResponse(
                    db_books_count=data["db_books_count"],
                    db_authors_count=data["db_authors_count"],
                    db_series_count=data["db_series_count"],
                    cached=True,
                )

            async with app.models.AsyncSessionLocal() as session:
                books_result = await session.execute(
                    sqlalchemy.text(
                        "SELECT COUNT(*) FROM books.books WHERE language = 'en'"
                    )
                )
                db_books_count = books_result.scalar_one()

                authors_result = await session.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM books.authors")
                )
                db_authors_count = authors_result.scalar_one()

                series_result = await session.execute(
                    sqlalchemy.text("SELECT COUNT(*) FROM books.series")
                )
                db_series_count = series_result.scalar_one()

            cache_data = {
                "db_books_count": db_books_count,
                "db_authors_count": db_authors_count,
                "db_series_count": db_series_count,
            }
            redis_client.setex(
                _COVERAGE_CACHE_KEY, _COVERAGE_CACHE_TTL, json.dumps(cache_data)
            )

            logger.info(
                f"Data coverage: {db_books_count} books, {db_authors_count} authors, {db_series_count} series"
            )

            return ingestion_pb2.GetDataCoverageResponse(
                db_books_count=db_books_count,
                db_authors_count=db_authors_count,
                db_series_count=db_series_count,
                cached=False,
            )

        except Exception as e:
            logger.error(f"Error getting data coverage: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.GetDataCoverageResponse()

    async def ImportDump(self, request, context):
        try:
            is_running = redis_client.exists("dump_import_running")
            if is_running:
                return ingestion_pb2.ImportDumpResponse(
                    status="already_running",
                    message="Dump import is already in progress",
                )

            saved_state = app.workers.dump.get_job_state(redis_client)
            if saved_state and len(saved_state.get("completed_phases", [])) < 6:
                job_id = saved_state["job_id"]
                completed = saved_state["completed_phases"]
                asyncio.create_task(
                    app.workers.dump.run_import_dump(job_id, redis_client)
                )
                return ingestion_pb2.ImportDumpResponse(
                    status="resuming",
                    message=(
                        f"Resuming dump import (job_id: {job_id}), "
                        f"phases already completed: {completed}"
                    ),
                )

            import uuid
            job_id = str(uuid.uuid4())
            asyncio.create_task(app.workers.dump.run_import_dump(job_id, redis_client))

            return ingestion_pb2.ImportDumpResponse(
                status="started",
                message=f"Dump import started (job_id: {job_id}). Check service logs for progress.",
            )

        except Exception as e:
            logger.error(f"Error starting dump import: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.ImportDumpResponse()

    async def RunCleanup(self, request, context):
        try:
            is_running = redis_client.get(_CLEANUP_RUNNING_KEY)
            if is_running:
                return ingestion_pb2.RunCleanupResponse(
                    status="already_running",
                    message="Cleanup job is already in progress",
                )

            asyncio.create_task(app.workers.data_cleaner.run_cleanup_job(force=True))

            return ingestion_pb2.RunCleanupResponse(
                status="started",
                message="Cleanup job started. Check service logs for progress.",
            )

        except Exception as e:
            logger.error(f"Error triggering cleanup: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.RunCleanupResponse()


async def serve():
    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        interceptors=app.tracing.get_server_interceptors(),
    )
    ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(
        IngestionService(), server
    )

    listen_addr = f"{app.config.settings.ingestion_service_host}:{app.config.settings.ingestion_grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting Ingestion gRPC server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()
