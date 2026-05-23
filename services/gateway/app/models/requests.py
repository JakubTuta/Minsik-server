import pydantic


class DataCoverageResponse(pydantic.BaseModel):
    db_books_count: int
    db_authors_count: int
    db_series_count: int
    cached: bool

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "db_books_count": 12453,
                "db_authors_count": 8721,
                "db_series_count": 342,
                "cached": False,
            }
        }
    )


class ImportDumpResponse(pydantic.BaseModel):
    status: str
    message: str

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "status": "started",
                "message": "Dump import started (job_id: abc123...). Check service logs for progress.",
            }
        }
    )


class JobTriggerResponse(pydantic.BaseModel):
    status: str
    message: str
