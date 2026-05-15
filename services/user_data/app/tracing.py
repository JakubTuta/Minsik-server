import typing

import app.config
import grpc
from ledger import LedgerClient
from ledger.tracing import get_tracer, propagation

_ledger: typing.Optional[LedgerClient] = None


class TracingServerInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(
        self,
        continuation: typing.Callable,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler:
        tracer = get_tracer()
        if tracer is None:
            return await continuation(handler_call_details)

        metadata_dict = dict(handler_call_details.invocation_metadata)
        ctx = propagation.extract(metadata_dict)
        method = handler_call_details.method

        handler = await continuation(handler_call_details)
        if handler is None:
            return None

        if handler.unary_unary is not None:
            original = handler.unary_unary

            async def traced_unary_unary(
                request: typing.Any, context: grpc.aio.ServicerContext
            ) -> typing.Any:
                with tracer.start_as_current_span(f"grpc.server{method}", parent=ctx):
                    return await original(request, context)

            return handler._replace(unary_unary=traced_unary_unary)

        return handler


def init_ledger() -> typing.Optional[LedgerClient]:
    global _ledger
    if app.config.settings.env == "production" and app.config.settings.ledger_api_key:
        _ledger = LedgerClient(
            api_key=app.config.settings.ledger_api_key,
            base_url="https://ledger-server.jtuta.cloud",
            service_name="user-data",
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
