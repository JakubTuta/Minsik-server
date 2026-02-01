import grpc
import logging
import uuid
import asyncio
import json
from concurrent import futures
from datetime import datetime
from redis import Redis
from rq import Queue

from app.config import settings
from app.workers import process_ingestion_job

try:
    from app.proto import ingestion_pb2, ingestion_pb2_grpc
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from proto import ingestion_pb2, ingestion_pb2_grpc

logger = logging.getLogger(__name__)

redis_client = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password if settings.redis_password else None,
    decode_responses=True
)

task_queue = Queue('ingestion', connection=redis_client)


class IngestionService(ingestion_pb2_grpc.IngestionServiceServicer):
    async def TriggerIngestion(self, request, context):
        try:
            total_books = request.total_books
            source = request.source or "both"
            language = request.language or "en"

            if total_books <= 0:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("total_books must be greater than 0")
                return ingestion_pb2.TriggerIngestionResponse()

            if source not in ["open_library", "google_books", "both"]:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("source must be one of: open_library, google_books, both")
                return ingestion_pb2.TriggerIngestionResponse()

            job_id = str(uuid.uuid4())

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: task_queue.enqueue(
                    'app.workers.ingestion_worker.run_ingestion_job_sync',
                    job_id,
                    total_books,
                    source,
                    language,
                    job_id=job_id,
                    job_timeout='1h'
                )
            )

            job_data = {
                "job_id": job_id,
                "status": "pending",
                "processed": 0,
                "total": total_books,
                "successful": 0,
                "failed": 0,
                "error": None,
                "started_at": int(datetime.now().timestamp()),
                "completed_at": None
            }
            redis_client.setex(f"ingestion_job:{job_id}", 3600, json.dumps(job_data))

            logger.info(f"Triggered ingestion job {job_id}: {total_books} books from {source} ({language})")

            return ingestion_pb2.TriggerIngestionResponse(
                job_id=job_id,
                status="pending",
                total_books=total_books,
                message=f"Ingestion job started: {total_books} books from {source}"
            )

        except Exception as e:
            logger.error(f"Error triggering ingestion: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.TriggerIngestionResponse()

    async def GetIngestionStatus(self, request, context):
        try:
            job_id = request.job_id

            if not job_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("job_id is required")
                return ingestion_pb2.GetIngestionStatusResponse()

            job_data_str = redis_client.get(f"ingestion_job:{job_id}")

            if not job_data_str:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Job {job_id} not found")
                return ingestion_pb2.GetIngestionStatusResponse()

            job_data = json.loads(job_data_str)

            return ingestion_pb2.GetIngestionStatusResponse(
                job_id=job_id,
                status=job_data.get("status", "unknown"),
                processed=job_data.get("processed", 0),
                total=job_data.get("total", 0),
                successful=job_data.get("successful", 0),
                failed=job_data.get("failed", 0),
                error=job_data.get("error") or "",
                started_at=job_data.get("started_at", 0),
                completed_at=job_data.get("completed_at", 0)
            )

        except Exception as e:
            logger.error(f"Error getting ingestion status: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.GetIngestionStatusResponse()

    async def CancelIngestion(self, request, context):
        try:
            job_id = request.job_id

            if not job_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("job_id is required")
                return ingestion_pb2.CancelIngestionResponse()

            job_data_str = redis_client.get(f"ingestion_job:{job_id}")

            if not job_data_str:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Job {job_id} not found")
                return ingestion_pb2.CancelIngestionResponse()

            job_data = json.loads(job_data_str)
            job_data["status"] = "cancelled"
            job_data["completed_at"] = int(datetime.now().timestamp())
            redis_client.setex(f"ingestion_job:{job_id}", 3600, json.dumps(job_data))

            logger.info(f"Cancelled ingestion job {job_id}")

            return ingestion_pb2.CancelIngestionResponse(
                success=True,
                message=f"Job {job_id} cancelled successfully"
            )

        except Exception as e:
            logger.error(f"Error cancelling ingestion: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ingestion_pb2.CancelIngestionResponse(success=False, message=str(e))


async def serve():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    ingestion_pb2_grpc.add_IngestionServiceServicer_to_server(IngestionService(), server)

    listen_addr = f"{settings.ingestion_service_host}:{settings.ingestion_grpc_port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting Ingestion gRPC server on {listen_addr}")
    await server.start()
    await server.wait_for_termination()
