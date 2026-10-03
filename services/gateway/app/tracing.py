import asyncio
import time
import typing

import app.config
import grpc
import ledger
import opentelemetry.metrics as metrics_api
import opentelemetry.trace as trace_api
from opentelemetry import propagate

_TRACE_SAMPLE_RATE = 0.05

_ledger: typing.Optional[ledger.LedgerClient] = None
_client_interceptor: typing.Optional["TracingClientInterceptor"] = None

_meter = metrics_api.get_meter(__name__)
_client_duration = _meter.create_histogram(
    "grpc_client_duration_ms",
    unit="ms",
    description="Gateway-side gRPC call duration by method and status code",
)
_client_errors = _meter.create_counter(
    "grpc_client_errors",
    description="Gateway-side gRPC calls that finished with a non-OK status",
)


def _record_call(method: str, status: str, started: float) -> None:
    attributes = {"method": method, "status": status}
    _client_duration.record((time.perf_counter() - started) * 1000, attributes)
    if status != "OK":
        _client_errors.add(1, attributes)


class _MutableClientCallDetails:
    def __init__(self, details: grpc.aio.ClientCallDetails, metadata: list) -> None:
        self.method = details.method
        self.timeout = details.timeout
        self.metadata = metadata
        self.credentials = details.credentials
        self.wait_for_ready = details.wait_for_ready


class TracingClientInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    async def intercept_unary_unary(
        self,
        continuation: typing.Callable,
        client_call_details: grpc.aio.ClientCallDetails,
        request: typing.Any,
    ) -> typing.Any:
        tracer = trace_api.get_tracer(__name__)

        method = client_call_details.method
        if isinstance(method, bytes):
            method = method.decode()

        started = time.perf_counter()
        status = "UNKNOWN"
        try:
            with tracer.start_as_current_span(f"grpc.client{method}", kind=trace_api.SpanKind.CLIENT):
                carrier: dict[str, str] = {}
                propagate.inject(carrier)

                metadata = list(client_call_details.metadata or [])
                for k, v in carrier.items():
                    metadata.append((k, v))

                new_details = _MutableClientCallDetails(client_call_details, metadata)
                call = await continuation(new_details, request)
                response = await call
            status = "OK"
            return response
        except grpc.aio.AioRpcError as error:
            status = error.code().name
            raise
        except asyncio.CancelledError:
            status = "CANCELLED"
            raise
        finally:
            _record_call(method, status, started)


def init_ledger() -> typing.Optional[ledger.LedgerClient]:
    global _ledger, _client_interceptor
    if app.config.settings.env == "production" and app.config.settings.ledger_api_key:
        _ledger = ledger.LedgerClient(
            api_key=app.config.settings.ledger_api_key,
            base_url="https://ledger-server.jtuta.cloud",
            service_name="gateway",
            environment=app.config.settings.env,
            trace_sample_rate=_TRACE_SAMPLE_RATE,
        )
        _ledger.instrument_logging()
        _client_interceptor = TracingClientInterceptor()
    return _ledger


def get_client_interceptors() -> list:
    if _client_interceptor is not None:
        return [_client_interceptor]
    return []


async def shutdown() -> None:
    global _ledger
    if _ledger is not None:
        await _ledger.shutdown()
        _ledger = None
