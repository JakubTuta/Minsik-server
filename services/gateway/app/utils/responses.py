import logging
import typing

import fastapi
import grpc

import app.models.responses

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


def success_response(data: typing.Any, status_code: int = 200) -> fastapi.responses.JSONResponse:
    response = app.models.responses.APIResponse(
        success=True,
        data=data,
        error=None
    )
    return fastapi.responses.JSONResponse(
        status_code=status_code,
        content=response.model_dump()
    )


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


def recommendation_section_to_dict(key: str, item: typing.Any) -> typing.Dict[str, typing.Any]:
    item_type = item.item_type
    result = {
        "key": key,
        "display_name": item.display_name,
        "title_params": dict(item.title_params),
        "item_type": item_type,
        "total": item.total,
    }
    if item_type == "book":
        result["book_items"] = [
            {
                "book_id": i.book_id,
                "work_id": i.work_id or None,
                "title": i.title,
                "slug": i.slug,
                "language": i.language,
                "primary_cover_url": i.primary_cover_url or None,
                "author_names": list(i.author_names),
                "author_slugs": list(i.author_slugs),
                "avg_rating": float(i.avg_rating) if i.avg_rating else 0.0,
                "rating_count": i.rating_count,
                "readers": i.readers,
                "score": i.score,
            }
            for i in item.book_items
        ]
    else:
        result["author_items"] = [
            {
                "author_id": i.author_id,
                "name": i.name,
                "slug": i.slug,
                "photo_url": i.photo_url or None,
                "book_count": i.book_count,
                "avg_rating": float(i.avg_rating) if i.avg_rating else 0.0,
                "rating_count": i.rating_count,
                "readers": i.readers,
                "score": i.score,
            }
            for i in item.author_items
        ]
    return result
