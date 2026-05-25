from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class GetDataCoverageRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetDataCoverageResponse(_message.Message):
    __slots__ = ("db_books_count", "db_authors_count", "db_series_count", "cached")
    DB_BOOKS_COUNT_FIELD_NUMBER: _ClassVar[int]
    DB_AUTHORS_COUNT_FIELD_NUMBER: _ClassVar[int]
    DB_SERIES_COUNT_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    db_books_count: int
    db_authors_count: int
    db_series_count: int
    cached: bool
    def __init__(self, db_books_count: _Optional[int] = ..., db_authors_count: _Optional[int] = ..., db_series_count: _Optional[int] = ..., cached: bool = ...) -> None: ...

class ImportDumpRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ImportDumpResponse(_message.Message):
    __slots__ = ("status", "message", "authors_count", "wikidata_count", "works_count", "editions_enriched", "editions_new_lang_rows", "ratings_count", "reading_log_count")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    AUTHORS_COUNT_FIELD_NUMBER: _ClassVar[int]
    WIKIDATA_COUNT_FIELD_NUMBER: _ClassVar[int]
    WORKS_COUNT_FIELD_NUMBER: _ClassVar[int]
    EDITIONS_ENRICHED_FIELD_NUMBER: _ClassVar[int]
    EDITIONS_NEW_LANG_ROWS_FIELD_NUMBER: _ClassVar[int]
    RATINGS_COUNT_FIELD_NUMBER: _ClassVar[int]
    READING_LOG_COUNT_FIELD_NUMBER: _ClassVar[int]
    status: str
    message: str
    authors_count: int
    wikidata_count: int
    works_count: int
    editions_enriched: int
    editions_new_lang_rows: int
    ratings_count: int
    reading_log_count: int
    def __init__(self, status: _Optional[str] = ..., message: _Optional[str] = ..., authors_count: _Optional[int] = ..., wikidata_count: _Optional[int] = ..., works_count: _Optional[int] = ..., editions_enriched: _Optional[int] = ..., editions_new_lang_rows: _Optional[int] = ..., ratings_count: _Optional[int] = ..., reading_log_count: _Optional[int] = ...) -> None: ...

class RunCleanupRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class RunCleanupResponse(_message.Message):
    __slots__ = ("status", "message")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    status: str
    message: str
    def __init__(self, status: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...
