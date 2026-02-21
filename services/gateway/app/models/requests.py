import typing

import pydantic


class TriggerIngestionRequest(pydantic.BaseModel):
    total_books: int = pydantic.Field(
        gt=0, description="Number of books to ingest (must be greater than 0)"
    )
    source: str = pydantic.Field(
        default="both",
        pattern="^(open_library|google_books|both)$",
        description="Data source for ingestion",
    )
    language: str = pydantic.Field(
        default="en", min_length=2, max_length=10, description="Language code for books"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {"total_books": 100, "source": "both", "language": "en"}
        }
    )


class TriggerIngestionResponse(pydantic.BaseModel):
    job_id: str
    status: str
    total_books: int
    processed: int
    successful: int
    failed: int
    error_message: typing.Optional[str]

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "total_books": 100,
                "processed": 98,
                "successful": 95,
                "failed": 3,
                "error_message": None,
            }
        }
    )


class DataCoverageResponse(pydantic.BaseModel):
    db_books_count: int
    db_authors_count: int
    db_series_count: int
    ol_english_total: int
    coverage_percent: float
    cached: bool

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "db_books_count": 12453,
                "db_authors_count": 8721,
                "db_series_count": 342,
                "ol_english_total": 10000000,
                "coverage_percent": 0.12,
                "cached": False,
            }
        }
    )


class SearchBookRequest(pydantic.BaseModel):
    title: str = pydantic.Field(min_length=1, description="Book title to search for")
    author: str = pydantic.Field(default="", description="Author name (optional)")
    source: str = pydantic.Field(
        default="both",
        pattern="^(open_library|google_books|both)$",
        description="Data source for search",
    )
    limit: int = pydantic.Field(
        default=10, ge=1, le=40, description="Maximum number of results to return"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "title": "1984",
                "author": "George Orwell",
                "source": "both",
                "limit": 10,
            }
        }
    )


class BookResult(pydantic.BaseModel):
    title: str
    authors: list[str]
    description: str
    publication_year: int
    language: str
    page_count: int
    cover_url: str
    isbn: list[str]
    publisher: str
    genres: list[str]
    open_library_id: str
    google_books_id: str
    source: str

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "title": "1984",
                "authors": ["George Orwell"],
                "description": "A dystopian novel set in Oceania...",
                "publication_year": 1949,
                "language": "en",
                "page_count": 328,
                "cover_url": "https://covers.openlibrary.org/b/id/7222246-L.jpg",
                "isbn": ["9780451524935", "0451524934"],
                "publisher": "Signet Classics",
                "genres": ["Fiction", "Dystopia", "Classics"],
                "open_library_id": "OL468431W",
                "google_books_id": "",
                "source": "open_library",
            }
        }
    )


class SearchBookResponse(pydantic.BaseModel):
    total_results: int
    books: list[BookResult]

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "total_results": 5,
                "books": [
                    {
                        "title": "1984",
                        "authors": ["George Orwell"],
                        "description": "A dystopian novel...",
                        "publication_year": 1949,
                        "language": "en",
                        "page_count": 328,
                        "cover_url": "https://covers.openlibrary.org/b/id/7222246-L.jpg",
                        "isbn": ["9780451524935"],
                        "publisher": "Signet Classics",
                        "genres": ["Fiction", "Dystopia"],
                        "open_library_id": "OL468431W",
                        "google_books_id": "",
                        "source": "open_library",
                    }
                ],
            }
        }
    )


class IngestionStatusResponse(pydantic.BaseModel):
    job_id: str
    status: str
    processed: int
    total: int
    successful: int
    failed: int
    error: str
    started_at: int
    completed_at: int


class CancelIngestionResponse(pydantic.BaseModel):
    success: bool
    message: str


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
