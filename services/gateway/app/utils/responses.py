import typing
import fastapi
import app.models.responses


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
