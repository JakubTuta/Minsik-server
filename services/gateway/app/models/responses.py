import typing
import pydantic


class ErrorDetail(pydantic.BaseModel):
    code: str
    message: str
    details: typing.Dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class APIResponse(pydantic.BaseModel):
    success: bool
    data: typing.Optional[typing.Any] = None
    error: typing.Optional[ErrorDetail] = None

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"key": "value"},
                "error": None
            }
        }
    )


class HealthResponse(pydantic.BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


class DeepHealthResponse(pydantic.BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    dependencies: typing.Dict[str, str]
