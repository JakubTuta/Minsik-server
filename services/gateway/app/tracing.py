import typing

import app.config
import grpc
import ledger
import ledger.tracing

_ledger: typing.Optional[ledger.LedgerClient] = None
_client_interceptor: typing.Optional["TracingClientInterceptor"] = None


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
        tracer = ledger.tracing.get_tracer()
        if tracer is None:
            return await continuation(client_call_details, request)

        method = client_call_details.method
        if isinstance(method, bytes):
            method = method.decode()

        with tracer.start_as_current_span(f"grpc.client{method}") as span:
            carrier: dict[str, str] = {}
            ledger.tracing.propagation.inject(carrier, span)

            metadata = list(client_call_details.metadata or [])
            for k, v in carrier.items():
                metadata.append((k, v))

            new_details = _MutableClientCallDetails(client_call_details, metadata)
            return await continuation(new_details, request)


def init_ledger() -> typing.Optional[ledger.LedgerClient]:
    global _ledger, _client_interceptor
    if app.config.settings.env == "production" and app.config.settings.ledger_api_key:
        _ledger = ledger.LedgerClient(
            api_key=app.config.settings.ledger_api_key,
            base_url="https://ledger-server.jtuta.cloud",
            service_name="gateway",
        )
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
