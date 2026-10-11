import logging
import typing

import fastapi
import grpc

import app.utils.responses

# gRPC status -> (HTTP status, error code, whether the service's own message may reach the client).
# Messages from the "caller did something wrong" codes are written by our services on purpose;
# everything else can carry an exception string, so the client gets a fixed sentence instead.
_MAPPING: typing.Dict[grpc.StatusCode, typing.Tuple[int, str, bool]] = {
    grpc.StatusCode.NOT_FOUND: (404, "NOT_FOUND", True),
    grpc.StatusCode.INVALID_ARGUMENT: (400, "INVALID_ARGUMENT", True),
    grpc.StatusCode.OUT_OF_RANGE: (400, "INVALID_ARGUMENT", True),
    grpc.StatusCode.ALREADY_EXISTS: (409, "ALREADY_EXISTS", True),
    grpc.StatusCode.FAILED_PRECONDITION: (409, "FAILED_PRECONDITION", True),
    grpc.StatusCode.UNAUTHENTICATED: (401, "UNAUTHENTICATED", False),
    grpc.StatusCode.PERMISSION_DENIED: (403, "PERMISSION_DENIED", True),
    grpc.StatusCode.RESOURCE_EXHAUSTED: (429, "RATE_LIMITED", False),
    grpc.StatusCode.UNAVAILABLE: (503, "SERVICE_UNAVAILABLE", False),
    grpc.StatusCode.DEADLINE_EXCEEDED: (504, "UPSTREAM_TIMEOUT", False),
}

_GENERIC_MESSAGES: typing.Dict[str, str] = {
    "UNAUTHENTICATED": "Authentication required",
    "RATE_LIMITED": "Too many requests",
    "SERVICE_UNAVAILABLE": "Service temporarily unavailable",
    "UPSTREAM_TIMEOUT": "The service took too long to respond",
    "INTERNAL_ERROR": "An internal error occurred",
}


def to_http_error(e: grpc.RpcError) -> typing.Tuple[int, str, str]:
    """HTTP status, error code and client-safe message for a failed gRPC call."""
    status, code, expose = _MAPPING.get(e.code(), (500, "INTERNAL_ERROR", False))
    details = e.details() or ""
    if expose and details:
        return status, code, details

    return status, code, _GENERIC_MESSAGES.get(code, "Request failed")


def error_response_for(e: grpc.RpcError) -> fastapi.responses.JSONResponse:
    status, code, message = to_http_error(e)
    return app.utils.responses.error_response(
        code=code,
        message=message,
        details={"grpc_code": e.code().name},
        status_code=status,
    )


async def handle_rpc_error(
    request: fastapi.Request, e: grpc.RpcError
) -> fastapi.responses.JSONResponse:
    """Last-resort handler for a gRPC failure no route dealt with itself."""
    app.utils.responses.log_grpc_error(
        logging.getLogger(__name__), f"on {request.method} {request.url.path}", e
    )
    return error_response_for(e)
