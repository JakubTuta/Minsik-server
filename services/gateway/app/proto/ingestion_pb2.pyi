from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

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

class SearchBookRequest(_message.Message):
    __slots__ = ("title", "author", "source", "limit")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    AUTHOR_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    title: str
    author: str
    source: str
    limit: int
    def __init__(self, title: _Optional[str] = ..., author: _Optional[str] = ..., source: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class BookResult(_message.Message):
    __slots__ = ("title", "authors", "description", "publication_year", "language", "page_count", "cover_url", "isbn", "publisher", "genres", "open_library_id", "google_books_id", "source")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    AUTHORS_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PUBLICATION_YEAR_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    PAGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    COVER_URL_FIELD_NUMBER: _ClassVar[int]
    ISBN_FIELD_NUMBER: _ClassVar[int]
    PUBLISHER_FIELD_NUMBER: _ClassVar[int]
    GENRES_FIELD_NUMBER: _ClassVar[int]
    OPEN_LIBRARY_ID_FIELD_NUMBER: _ClassVar[int]
    GOOGLE_BOOKS_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    title: str
    authors: _containers.RepeatedScalarFieldContainer[str]
    description: str
    publication_year: int
    language: str
    page_count: int
    cover_url: str
    isbn: _containers.RepeatedScalarFieldContainer[str]
    publisher: str
    genres: _containers.RepeatedScalarFieldContainer[str]
    open_library_id: str
    google_books_id: str
    source: str
    def __init__(self, title: _Optional[str] = ..., authors: _Optional[_Iterable[str]] = ..., description: _Optional[str] = ..., publication_year: _Optional[int] = ..., language: _Optional[str] = ..., page_count: _Optional[int] = ..., cover_url: _Optional[str] = ..., isbn: _Optional[_Iterable[str]] = ..., publisher: _Optional[str] = ..., genres: _Optional[_Iterable[str]] = ..., open_library_id: _Optional[str] = ..., google_books_id: _Optional[str] = ..., source: _Optional[str] = ...) -> None: ...

class SearchBookResponse(_message.Message):
    __slots__ = ("total_results", "books")
    TOTAL_RESULTS_FIELD_NUMBER: _ClassVar[int]
    BOOKS_FIELD_NUMBER: _ClassVar[int]
    total_results: int
    books: _containers.RepeatedCompositeFieldContainer[BookResult]
    def __init__(self, total_results: _Optional[int] = ..., books: _Optional[_Iterable[_Union[BookResult, _Mapping]]] = ...) -> None: ...
