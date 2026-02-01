from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TriggerIngestionRequest(_message.Message):
    __slots__ = ("total_books", "source", "language")
    TOTAL_BOOKS_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    total_books: int
    source: str
    language: str
    def __init__(self, total_books: _Optional[int] = ..., source: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class TriggerIngestionResponse(_message.Message):
    __slots__ = ("job_id", "status", "total_books", "message")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BOOKS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    status: str
    total_books: int
    message: str
    def __init__(self, job_id: _Optional[str] = ..., status: _Optional[str] = ..., total_books: _Optional[int] = ..., message: _Optional[str] = ...) -> None: ...

class GetIngestionStatusRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class GetIngestionStatusResponse(_message.Message):
    __slots__ = ("job_id", "status", "processed", "total", "successful", "failed", "error", "started_at", "completed_at")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    FAILED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_AT_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    status: str
    processed: int
    total: int
    successful: int
    failed: int
    error: str
    started_at: int
    completed_at: int
    def __init__(self, job_id: _Optional[str] = ..., status: _Optional[str] = ..., processed: _Optional[int] = ..., total: _Optional[int] = ..., successful: _Optional[int] = ..., failed: _Optional[int] = ..., error: _Optional[str] = ..., started_at: _Optional[int] = ..., completed_at: _Optional[int] = ...) -> None: ...

class CancelIngestionRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class CancelIngestionResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...
