import logging
import typing

import app.config
import app.tracing
import grpc
import grpc_health.v1.health_pb2
import grpc_health.v1.health_pb2_grpc

logger = logging.getLogger(__name__)


class GrpcClientBase:
    service_label: str = ""

    def __init__(self):
        self.channel: typing.Optional[grpc.aio.Channel] = None
        self.stub: typing.Optional[typing.Any] = None

    def _target(self) -> str:
        raise NotImplementedError

    def _create_stub(self, channel: grpc.aio.Channel) -> typing.Any:
        raise NotImplementedError

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self) -> None:
        self.channel = grpc.aio.insecure_channel(
            self._target(),
            options=[
                ("grpc.keepalive_time_ms", app.config.settings.grpc_keepalive_time_ms),
                (
                    "grpc.keepalive_timeout_ms",
                    app.config.settings.grpc_keepalive_timeout_ms,
                ),
                ("grpc.keepalive_permit_without_calls", 0),
                ("grpc.http2.max_pings_without_data", 0),
                (
                    "grpc.max_receive_message_length",
                    app.config.settings.grpc_max_message_length,
                ),
            ],
            interceptors=app.tracing.get_client_interceptors(),
        )
        self.stub = self._create_stub(self.channel)
        logger.info(f"Connected to {self.service_label} service at {self._target()}")

    async def close(self) -> None:
        if self.channel:
            await self.channel.close()
            logger.info(f"Closed {self.service_label} service connection")

    async def health_check(self, timeout: float = 2.0) -> bool:
        """Whether the service behind this channel reports itself as serving.

        Uses grpc.health.v1 rather than a business RPC so the probe stays free
        of database work and cannot be mistaken for real traffic.
        """
        if self.channel is None:
            return False

        stub = grpc_health.v1.health_pb2_grpc.HealthStub(self.channel)
        response = await stub.Check(
            grpc_health.v1.health_pb2.HealthCheckRequest(), timeout=timeout
        )
        return (
            response.status
            == grpc_health.v1.health_pb2.HealthCheckResponse.SERVING
        )

    async def _call(
        self,
        method_name: str,
        request: typing.Any,
        timeout: typing.Optional[float] = None,
    ) -> typing.Any:
        method = getattr(self.stub, method_name)
        try:
            return await method(
                request, timeout=timeout or app.config.settings.grpc_timeout
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC {self.service_label}.{method_name} failed: "
                f"{e.code()} - {e.details()}"
            )
            raise
