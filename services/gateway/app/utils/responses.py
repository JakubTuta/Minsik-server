import logging
import typing

import fastapi
import grpc

import app.models.responses
import app.utils.proto

_CLIENT_ERROR_CODES = {
    grpc.StatusCode.NOT_FOUND,
    grpc.StatusCode.INVALID_ARGUMENT,
    grpc.StatusCode.ALREADY_EXISTS,
    grpc.StatusCode.UNAUTHENTICATED,
    grpc.StatusCode.PERMISSION_DENIED,
    grpc.StatusCode.FAILED_PRECONDITION,
    grpc.StatusCode.OUT_OF_RANGE,
    grpc.StatusCode.RESOURCE_EXHAUSTED,
}


def log_grpc_error(logger: logging.Logger, context: str, e: grpc.RpcError) -> None:
    msg = f"gRPC error {context}: {e.code()} - {e.details()}"
    if e.code() in _CLIENT_ERROR_CODES:
        logger.warning(msg)
    else:
        logger.error(msg)


def success_response(
    data: typing.Any,
    status_code: int = 200,
    cache_control: typing.Optional[str] = None,
    vary: typing.Optional[str] = None,
) -> fastapi.responses.JSONResponse:
    response = app.models.responses.APIResponse(
        success=True,
        data=data,
        error=None
    )
    headers: typing.Dict[str, str] = {}
    if cache_control:
        headers["Cache-Control"] = cache_control
    if vary:
        headers["Vary"] = vary
    return fastapi.responses.JSONResponse(
        status_code=status_code,
        content=response.model_dump(),
        headers=headers or None,
    )


# The language comes from ?language=, else the signed-in user, the pref_lang cookie or
# Accept-Language, so a shared cache must not hand one reader's language to another.
LANGUAGE_VARY = "Accept-Language, Cookie"


def error_response(
    code: str,
    message: str,
    details: typing.Dict[str, typing.Any] = None,
    status_code: int = 400
) -> fastapi.responses.JSONResponse:
    response = app.models.responses.APIResponse(
        success=False,
        data=None,
        error=app.models.responses.ErrorDetail(
            code=code,
            message=message,
            details=details or {}
        )
    )
    return fastapi.responses.JSONResponse(
        status_code=status_code,
        content=response.model_dump()
    )


def recommendation_section_to_dict(item: typing.Any) -> typing.Dict[str, typing.Any]:
    """A section carries book items or author items, never both."""
    section = app.utils.proto.message_to_dict(item)
    del section["author_items" if item.item_type == "book" else "book_items"]
    return section
