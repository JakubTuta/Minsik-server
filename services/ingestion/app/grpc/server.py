import asyncio
import concurrent.futures
import json
import logging
import typing

import app.config
import app.models
import app.proto.ingestion_pb2
import app.proto.ingestion_pb2_grpc
import uuid
import app.tracing
import app.workers.data_cleaner
import app.workers.dump
import grpc
import grpc_health.v1.health
import grpc_health.v1.health_pb2
import grpc_health.v1.health_pb2_grpc
import redis
import sqlalchemy

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


_background_tasks: typing.Set[asyncio.Task] = set()


def _spawn_background(coro: typing.Coroutine) -> None:
    """Run a coroutine past the response without letting it be collected.

    The event loop holds only a weak reference to a task, so a plain
    fire-and-forget create_task can be garbage collected while it is
    suspended, and the work silently never finishes.
    """
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class IngestionService(app.proto.ingestion_pb2_grpc.IngestionServiceServicer):
    async def GetDataCoverage(self, request, context):
        try:
            cached = redis_client.get(_COVERAGE_CACHE_KEY)
            if cached:
                data = json.loads(cached)
                return app.proto.ingestion_pb2.GetDataCoverageResponse(
                    db_books_count=data["db_books_count"],
                    db_authors_count=data["db_authors_count"],
                    db_series_count=data["db_series_count"],
                    cached=True,
                )

            async with app.models.AsyncSessionLocal() as session:
                # Every row, not just the English ones: this is a raw inventory
                # shown next to the unfiltered author and series totals, and a
                # catalogue whose editions are mostly non-English would
                # otherwise report a near-empty database.
                #
                # An exact COUNT(*) forces Postgres to walk every row of the
                # table (no index makes that faster; MVCC visibility can't be
                # answered from an index alone), which is what made this
                # endpoint time out once books.books reached hundreds of
                # thousands of rows. reltuples is the planner's own row-count
                # estimate, refreshed by autovacuum/ANALYZE, and a dashboard
                # stat has no need to be exact to the row.
                counts_result = await session.execute(
                    sqlalchemy.text(
                        """
                        SELECT relname, reltuples::bigint
                        FROM pg_class
                        WHERE oid IN (
                            'books.books'::regclass,
                            'books.authors'::regclass,
                            'books.series'::regclass
                        )
                        """
                    )
                )
                estimates = {row.relname: max(row[1], 0) for row in counts_result}
                db_books_count = estimates.get("books", 0)
                db_authors_count = estimates.get("authors", 0)
                db_series_count = estimates.get("series", 0)

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

            return app.proto.ingestion_pb2.GetDataCoverageResponse(
                db_books_count=db_books_count,
                db_authors_count=db_authors_count,
                db_series_count=db_series_count,
                cached=False,
            )

        except Exception as e:
            logger.error(f"Error getting data coverage: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return app.proto.ingestion_pb2.GetDataCoverageResponse()

    async def ImportDump(self, request, context):
        try:
            is_running = redis_client.exists("dump_import_running")
            if is_running:
                return app.proto.ingestion_pb2.ImportDumpResponse(
                    status="already_running",
                    message="Dump import is already in progress",
                )

            saved_state = app.workers.dump.get_job_state(redis_client)
            if saved_state and len(saved_state.get("completed_phases", [])) < 6:
                job_id = saved_state["job_id"]
                completed = saved_state["completed_phases"]
                _spawn_background(
                    app.workers.dump.run_import_dump(job_id, redis_client)
                )
                return app.proto.ingestion_pb2.ImportDumpResponse(
                    status="resuming",
                    message=(
                        f"Resuming dump import (job_id: {job_id}), "
                        f"phases already completed: {completed}"
                    ),
                )

            job_id = str(uuid.uuid4())
            _spawn_background(app.workers.dump.run_import_dump(job_id, redis_client))

            return app.proto.ingestion_pb2.ImportDumpResponse(
                status="started",
                message=f"Dump import started (job_id: {job_id}). Check service logs for progress.",
            )

        except Exception as e:
            logger.error(f"Error starting dump import: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return app.proto.ingestion_pb2.ImportDumpResponse()

    async def RunCleanup(self, request, context):
        try:
            is_running = redis_client.get(_CLEANUP_RUNNING_KEY)
            if is_running:
                return app.proto.ingestion_pb2.RunCleanupResponse(
                    status="already_running",
                    message="Cleanup job is already in progress",
                )

            _spawn_background(app.workers.data_cleaner.run_cleanup_job(force=True))

            return app.proto.ingestion_pb2.RunCleanupResponse(
                status="started",
                message="Cleanup job started. Check service logs for progress.",
            )

        except Exception as e:
            logger.error(f"Error triggering cleanup: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return app.proto.ingestion_pb2.RunCleanupResponse()


async def serve():
    server = grpc.aio.server(
        concurrent.futures.ThreadPoolExecutor(max_workers=10),
        interceptors=app.tracing.get_server_interceptors(),
    )
    app.proto.ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(
        IngestionService(), server
    )

    health_servicer = grpc_health.v1.health.aio.HealthServicer()
    grpc_health.v1.health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    listen_addr = f"{app.config.settings.ingestion_service_host}:{app.config.settings.ingestion_grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting Ingestion gRPC server on {listen_addr}")
    await server.start()
    await health_servicer.set(
        "", grpc_health.v1.health_pb2.HealthCheckResponse.SERVING
    )
    await server.wait_for_termination()
