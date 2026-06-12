import logging
import app.config
from app.grpc_clients import base
import app.proto.ingestion_pb2
import app.proto.ingestion_pb2_grpc

logger = logging.getLogger(__name__)


class IngestionClient(base.GrpcClientBase):
    service_label = "ingestion"

    def _target(self) -> str:
        return app.config.settings.ingestion_service_url

    def _create_stub(self, channel):
        return app.proto.ingestion_pb2_grpc.IngestionServiceStub(channel)


    async def get_data_coverage(self) -> app.proto.ingestion_pb2.GetDataCoverageResponse:
        request = app.proto.ingestion_pb2.GetDataCoverageRequest()

        return await self._call("GetDataCoverage", request, timeout=app.config.settings.grpc_admin_timeout)

    async def import_dump(self) -> app.proto.ingestion_pb2.ImportDumpResponse:
        request = app.proto.ingestion_pb2.ImportDumpRequest()

        return await self._call("ImportDump", request)

    async def run_cleanup(self) -> app.proto.ingestion_pb2.RunCleanupResponse:
        request = app.proto.ingestion_pb2.RunCleanupRequest()

        return await self._call("RunCleanup", request, timeout=app.config.settings.grpc_admin_timeout)


ingestion_client = IngestionClient()
