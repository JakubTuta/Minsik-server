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

_meter = metrics_api.get_meter(__name__)
_server_duration = _meter.create_histogram(
    "grpc_server_duration_ms",
    unit="ms",
    description="Server-side gRPC handler duration by method and status code",
)
_server_errors = _meter.create_counter(
    "grpc_server_errors",
    description="Server-side gRPC calls that finished with a non-OK status",
)


def _status_name(context: grpc.aio.ServicerContext) -> str:
    code = context.code()
    return "OK" if code is None else code.name


def _record_call(method: str, status: str, started: float) -> None:
    attributes = {"method": method, "status": status}
    _server_duration.record((time.perf_counter() - started) * 1000, attributes)
    if status != "OK":
        _server_errors.add(1, attributes)


class TracingServerInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(
        self,
        continuation: typing.Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        tracer = trace_api.get_tracer(__name__)

        metadata_dict = dict(handler_call_details.invocation_metadata)
        ctx = propagate.extract(metadata_dict)
        method = handler_call_details.method

        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        if handler.unary_unary is not None:
            original = handler.unary_unary

            async def traced_unary_unary(
                request: typing.Any, context: grpc.aio.ServicerContext
            ) -> typing.Any:
                started = time.perf_counter()
                status = "UNKNOWN"
                try:
                    with tracer.start_as_current_span(
                        f"grpc.server{method}", kind=trace_api.SpanKind.SERVER, context=ctx
                    ):
                        response = await original(request, context)
                    status = _status_name(context)
                    return response
                except grpc.aio.AbortError:
                    status = _status_name(context)
                    raise
                except asyncio.CancelledError:
                    status = "CANCELLED"
                    raise
                finally:
                    _record_call(method, status, started)

            return handler._replace(unary_unary=traced_unary_unary)

        return handler


def init_ledger() -> typing.Optional[ledger.LedgerClient]:
    global _ledger
    if app.config.settings.env == "production" and app.config.settings.ledger_api_key:
        _ledger = ledger.LedgerClient(
            api_key=app.config.settings.ledger_api_key,
            base_url="https://ledger-server.jtuta.cloud",
            service_name="recommendation",
            environment=app.config.settings.env,
            trace_sample_rate=_TRACE_SAMPLE_RATE,
        )
        _ledger.instrument_logging()
    return _ledger


def get_server_interceptors() -> list:
    if _ledger is not None:
        return [TracingServerInterceptor()]
    return []


async def shutdown() -> None:
    global _ledger
    if _ledger is not None:
        await _ledger.shutdown()
        _ledger = None
