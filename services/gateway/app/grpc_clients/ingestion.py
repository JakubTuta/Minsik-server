import grpc
import logging
import typing
import app.config
import app.proto.ingestion_pb2 as ingestion_pb2
import app.proto.ingestion_pb2_grpc as ingestion_pb2_grpc

logger = logging.getLogger(__name__)


class IngestionClient:
    def __init__(self):
        self.channel: typing.Optional[grpc.aio.Channel] = None
        self.stub: typing.Optional[ingestion_pb2_grpc.IngestionServiceStub] = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        self.channel = grpc.aio.insecure_channel(
            app.config.settings.ingestion_service_url,
            options=[
                ("grpc.keepalive_time_ms", app.config.settings.grpc_keepalive_time_ms),
                ("grpc.keepalive_timeout_ms", app.config.settings.grpc_keepalive_timeout_ms),
                ("grpc.keepalive_permit_without_calls", 0),
                ("grpc.http2.max_pings_without_data", 0),
            ]
        )
        self.stub = ingestion_pb2_grpc.IngestionServiceStub(self.channel)
        logger.info(f"Connected to ingestion service at {app.config.settings.ingestion_service_url}")

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("Closed ingestion service connection")

    async def trigger_ingestion(self, total_books: int, source: str, language: str) -> ingestion_pb2.TriggerIngestionResponse:
        request = ingestion_pb2.TriggerIngestionRequest(
            total_books=total_books,
            source=source,
            language=language
        )

        try:
            response = await self.stub.TriggerIngestion(request, timeout=None)
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error triggering ingestion: {e.code()} - {e.details()}")
            raise

    async def search_book(self, title: str, author: str = "", source: str = "both", limit: int = 10) -> ingestion_pb2.SearchBookResponse:
        request = ingestion_pb2.SearchBookRequest(
            title=title,
            author=author,
            source=source,
            limit=limit
        )

        try:
            response = await self.stub.SearchBook(
                request,
                timeout=app.config.settings.grpc_admin_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error searching for book: {e.code()} - {e.details()}")
            raise

    async def get_data_coverage(self) -> ingestion_pb2.GetDataCoverageResponse:
        request = ingestion_pb2.GetDataCoverageRequest()

        try:
            response = await self.stub.GetDataCoverage(
                request,
                timeout=app.config.settings.grpc_admin_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting data coverage: {e.code()} - {e.details()}")
            raise

    async def import_dump(self) -> ingestion_pb2.ImportDumpResponse:
        request = ingestion_pb2.ImportDumpRequest()

        try:
            response = await self.stub.ImportDump(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error starting dump import: {e.code()} - {e.details()}")
            raise


ingestion_client = IngestionClient()
