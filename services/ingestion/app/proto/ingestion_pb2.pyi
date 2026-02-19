from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

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
    __slots__ = ("job_id", "status", "total_books", "processed", "successful", "failed", "error_message")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BOOKS_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_FIELD_NUMBER: _ClassVar[int]
    SUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    FAILED_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    status: str
    total_books: int
    processed: int
    successful: int
    failed: int
    error_message: str
    def __init__(self, job_id: _Optional[str] = ..., status: _Optional[str] = ..., total_books: _Optional[int] = ..., processed: _Optional[int] = ..., successful: _Optional[int] = ..., failed: _Optional[int] = ..., error_message: _Optional[str] = ...) -> None: ...

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

class GetDataCoverageRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetDataCoverageResponse(_message.Message):
    __slots__ = ("db_books_count", "db_authors_count", "db_series_count", "ol_english_total", "coverage_percent", "cached")
    DB_BOOKS_COUNT_FIELD_NUMBER: _ClassVar[int]
    DB_AUTHORS_COUNT_FIELD_NUMBER: _ClassVar[int]
    DB_SERIES_COUNT_FIELD_NUMBER: _ClassVar[int]
    OL_ENGLISH_TOTAL_FIELD_NUMBER: _ClassVar[int]
    COVERAGE_PERCENT_FIELD_NUMBER: _ClassVar[int]
    CACHED_FIELD_NUMBER: _ClassVar[int]
    db_books_count: int
    db_authors_count: int
    db_series_count: int
    ol_english_total: int
    coverage_percent: float
    cached: bool
    def __init__(self, db_books_count: _Optional[int] = ..., db_authors_count: _Optional[int] = ..., db_series_count: _Optional[int] = ..., ol_english_total: _Optional[int] = ..., coverage_percent: _Optional[float] = ..., cached: bool = ...) -> None: ...

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
