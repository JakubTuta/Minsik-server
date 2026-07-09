import typing

import app.config
import grpc
import ledger
import opentelemetry.trace as trace_api
from opentelemetry import propagate

_ledger: typing.Optional[ledger.LedgerClient] = None


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
                with tracer.start_as_current_span(
                    f"grpc.server{method}", kind=trace_api.SpanKind.SERVER, context=ctx
                ):
                    return await original(request, context)

            return handler._replace(unary_unary=traced_unary_unary)

        return handler


def init_ledger() -> typing.Optional[ledger.LedgerClient]:
    global _ledger
    if app.config.settings.env == "production" and app.config.settings.ledger_api_key:
        _ledger = ledger.LedgerClient(
            api_key=app.config.settings.ledger_api_key,
            base_url="https://ledger-server.jtuta.cloud",
            service_name="auth",
        )
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
