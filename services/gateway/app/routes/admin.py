import logging
import typing

import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit
import app.models.books_responses
import app.models.requests
import app.models.responses
import app.utils.responses
import fastapi
import grpc

router = fastapi.APIRouter(prefix="/api/v1/admin", tags=["Admin"])

logger = logging.getLogger(__name__)
limiter = app.middleware.rate_limit.limiter

_AUTH_RESPONSES = {
    401: {
        "description": "Authentication required",
        "content": {
            "application/json": {
                "example": {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Authentication required",
                        "details": {},
                    },
                }
            }
        },
    },
    403: {
        "description": "Admin privileges required",
        "content": {
            "application/json": {
                "example": {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Admin privileges required",
                        "details": {},
                    },
                }
            }
        },
    },
}


@router.post(
    "/ingestion/trigger",
    response_model=app.models.responses.APIResponse,
    summary="Trigger book ingestion",
    description="Ingest books from external APIs (Open Library and/or Google Books). Blocks until ingestion completes and returns final stats.",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {
            "description": "Ingestion completed",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "job_id": "550e8400-e29b-41d4-a716-446655440000",
                            "status": "completed",
                            "total_books": 100,
                            "processed": 98,
                            "successful": 95,
                            "failed": 3,
                            "error_message": None,
                        },
                        "error": None,
                    }
                }
            },
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "INVALID_ARGUMENT",
                            "message": "total_books must be greater than 0",
                            "details": {},
                        },
                    }
                }
            },
        },
        **_AUTH_RESPONSES,
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "Failed to communicate with ingestion service",
                            "details": {},
                        },
                    }
                }
            },
        },
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def trigger_ingestion(
    request: fastapi.Request,
    ingestion_request: app.models.requests.TriggerIngestionRequest,
):
    try:
        async with app.grpc_clients.IngestionClient() as client:
            response = await client.trigger_ingestion(
                total_books=ingestion_request.total_books,
                source=ingestion_request.source,
                language=ingestion_request.language,
            )

            data = app.models.requests.TriggerIngestionResponse(
                job_id=response.job_id,
                status=response.status,
                total_books=response.total_books,
                processed=response.processed,
                successful=response.successful,
                failed=response.failed,
                error_message=response.error_message or None,
            )

            return app.utils.responses.success_response(
                data.model_dump(), status_code=200
            )

    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            return app.utils.responses.error_response(
                code="INVALID_ARGUMENT", message=e.details(), status_code=400
            )
        else:
            return app.utils.responses.error_response(
                code="INTERNAL_ERROR",
                message="Failed to communicate with ingestion service",
                details={"grpc_code": e.code().name, "grpc_details": e.details()},
                status_code=500,
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.get(
    "/ingestion/status/{job_id}",
    response_model=app.models.responses.APIResponse,
    summary="Get ingestion job status",
    description="Check the status of a running or completed ingestion job.",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Job status retrieved"},
        **_AUTH_RESPONSES,
        404: {"description": "Job not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def get_ingestion_status(request: fastapi.Request, job_id: str):
    try:
        async with app.grpc_clients.IngestionClient() as client:
            response = await client.get_ingestion_status(job_id=job_id)

            data = app.models.requests.IngestionStatusResponse(
                job_id=response.job_id,
                status=response.status,
                processed=response.processed,
                total=response.total,
                successful=response.successful,
                failed=response.failed,
                error=response.error,
                started_at=response.started_at,
                completed_at=response.completed_at,
            )

            return app.utils.responses.success_response(data.model_dump())

    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        else:
            return app.utils.responses.error_response(
                code="INTERNAL_ERROR",
                message="Failed to communicate with ingestion service",
                details={"grpc_code": e.code().name, "grpc_details": e.details()},
                status_code=500,
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.delete(
    "/ingestion/cancel/{job_id}",
    response_model=app.models.responses.APIResponse,
    summary="Cancel an ingestion job",
    description="Cancel a running ingestion job.",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Job cancelled"},
        **_AUTH_RESPONSES,
        404: {"description": "Job not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def cancel_ingestion(request: fastapi.Request, job_id: str):
    try:
        async with app.grpc_clients.IngestionClient() as client:
            response = await client.cancel_ingestion(job_id=job_id)

            data = app.models.requests.CancelIngestionResponse(
                success=response.success, message=response.message
            )

            return app.utils.responses.success_response(data.model_dump())

    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        else:
            return app.utils.responses.error_response(
                code="INTERNAL_ERROR",
                message="Failed to communicate with ingestion service",
                details={"grpc_code": e.code().name, "grpc_details": e.details()},
                status_code=500,
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.get(
    "/ingestion/coverage",
    response_model=app.models.responses.APIResponse,
    summary="Get data coverage stats",
    description="Returns counts of books/authors/series in the database compared to Open Library's English catalog estimate.",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {
            "description": "Coverage stats retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "db_books_count": 12453,
                            "db_authors_count": 8721,
                            "db_series_count": 342,
                            "ol_english_total": 10000000,
                            "coverage_percent": 0.12,
                            "cached": False,
                        },
                        "error": None,
                    }
                }
            },
        },
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def get_data_coverage(request: fastapi.Request):
    try:
        async with app.grpc_clients.IngestionClient() as client:
            response = await client.get_data_coverage()

            data = app.models.requests.DataCoverageResponse(
                db_books_count=response.db_books_count,
                db_authors_count=response.db_authors_count,
                db_series_count=response.db_series_count,
                ol_english_total=response.ol_english_total,
                coverage_percent=response.coverage_percent,
                cached=response.cached,
            )

            return app.utils.responses.success_response(
                data.model_dump(), status_code=200
            )

    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to communicate with ingestion service",
            details={"grpc_code": e.code().name, "grpc_details": e.details()},
            status_code=500,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.post(
    "/books/search",
    response_model=app.models.responses.APIResponse,
    summary="Search for a specific book",
    description="Search for books by title and author from Open Library and/or Google Books APIs",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Search completed successfully"},
        **_AUTH_RESPONSES,
        400: {"description": "Invalid request parameters"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def search_book(
    request: fastapi.Request, search_request: app.models.requests.SearchBookRequest
):
    try:
        async with app.grpc_clients.IngestionClient() as client:
            response = await client.search_book(
                title=search_request.title,
                author=search_request.author,
                source=search_request.source,
                limit=search_request.limit,
            )

            books = []
            for book in response.books:
                books.append(
                    {
                        "title": book.title,
                        "authors": list(book.authors),
                        "description": book.description,
                        "publication_year": book.publication_year,
                        "language": book.language,
                        "page_count": book.page_count,
                        "cover_url": book.cover_url,
                        "isbn": list(book.isbn),
                        "publisher": book.publisher,
                        "genres": list(book.genres),
                        "open_library_id": book.open_library_id,
                        "google_books_id": book.google_books_id,
                        "source": book.source,
                    }
                )

            data = {"total_results": response.total_results, "books": books}

            return app.utils.responses.success_response(data, status_code=200)

    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")

        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            return app.utils.responses.error_response(
                code="INVALID_ARGUMENT", message=e.details(), status_code=400
            )
        else:
            return app.utils.responses.error_response(
                code="INTERNAL_ERROR",
                message="Failed to communicate with ingestion service",
                details={"grpc_code": e.code().name, "grpc_details": e.details()},
                status_code=500,
            )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.post(
    "/ingestion/import-dump",
    response_model=app.models.responses.APIResponse,
    summary="Import Open Library data dump",
    description="Trigger an import of Open Library's monthly data dump. Import runs asynchronously in the background; check service logs for progress.",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {
            "description": "Dump import started or already running",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "status": "started",
                            "message": "Dump import started (job_id: abc123...). Check service logs for progress.",
                        },
                        "error": None,
                    }
                }
            },
        },
        **_AUTH_RESPONSES,
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "Failed to start dump import",
                            "details": {},
                        },
                    }
                }
            },
        },
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def import_dump(request: fastapi.Request):
    try:
        async with app.grpc_clients.IngestionClient() as client:
            response = await client.import_dump()

            data = app.models.requests.ImportDumpResponse(
                status=response.status, message=response.message
            )

            return app.utils.responses.success_response(
                data.model_dump(), status_code=200
            )

    except grpc.RpcError as e:
        logger.error(f"gRPC error: {e.code()} - {e.details()}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to start dump import",
            details={"grpc_code": e.code().name, "grpc_details": e.details()},
            status_code=500,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.patch(
    "/books/{book_id}",
    response_model=app.models.books_responses.AdminBookUpdateResponse,
    summary="Update a book",
    description="""Partially update a book's editable fields. Only the fields included in
    the request body are changed — omitted fields are left untouched.
    Author/genre relationships cannot be modified through this endpoint.""",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Book updated successfully"},
        400: {"description": "No fields provided to update"},
        404: {"description": "Book not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def update_book(
    request: fastapi.Request,
    book_id: int,
    body: app.models.books_responses.AdminUpdateBookRequest,
):
    import json

    updates = body.model_dump(exclude_unset=True)

    if not updates:
        return app.utils.responses.error_response(
            code="NO_FIELDS",
            message="No fields provided to update",
            status_code=400,
        )

    proto_fields: typing.Dict[str, typing.Any] = {}
    for field, value in updates.items():
        if field == "formats":
            proto_fields["formats_json"] = json.dumps(value)
        elif field == "cover_history":
            proto_fields["cover_history_json"] = json.dumps(value)
        elif field == "isbn":
            proto_fields["isbn_json"] = json.dumps(value)
        elif field == "external_ids":
            proto_fields["external_ids_json"] = json.dumps(value)
        else:
            proto_fields[field] = value

    try:
        async with app.grpc_clients.BooksClient() as client:
            response = await client.update_book(book_id=book_id, fields=proto_fields)
            book = response.book
            return app.utils.responses.success_response(
                {
                    "book_id": book.book_id,
                    "title": book.title,
                    "slug": book.slug,
                    "description": book.description,
                    "first_sentence": book.first_sentence or None,
                    "language": book.language,
                    "original_publication_year": book.original_publication_year,
                    "primary_cover_url": book.primary_cover_url,
                    "cover_history": [
                        {"url": c.url, "width": c.width, "size": c.size}
                        for c in book.cover_history
                    ],
                    "formats": list(book.formats),
                    "isbn": list(book.isbn),
                    "publisher": book.publisher,
                    "number_of_pages": book.number_of_pages,
                    "external_ids": dict(book.external_ids),
                    "open_library_id": book.open_library_id,
                    "google_books_id": book.google_books_id,
                    "series": (
                        {
                            "series_id": book.series.series_id,
                            "name": book.series.name,
                            "slug": book.series.slug,
                            "total_books": book.series.total_books,
                        }
                        if book.HasField("series")
                        else None
                    ),
                    "series_position": book.series_position or None,
                    "rating_count": book.rating_count,
                    "avg_rating": book.avg_rating,
                    "ol_rating_count": book.ol_rating_count,
                    "ol_avg_rating": book.ol_avg_rating,
                    "updated_at": book.updated_at,
                }
            )
    except grpc.RpcError as e:
        logger.error(f"gRPC error updating book: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update book",
            details={"grpc_code": e.code().name, "grpc_details": e.details()},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error updating book: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.patch(
    "/authors/{author_id}",
    response_model=app.models.books_responses.AdminAuthorUpdateResponse,
    summary="Update an author",
    description="""Partially update an author's editable fields. Only the fields included
    in the request body are changed — omitted fields are left untouched.""",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Author updated successfully"},
        400: {"description": "No fields provided to update"},
        404: {"description": "Author not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def update_author(
    request: fastapi.Request,
    author_id: int,
    body: app.models.books_responses.AdminUpdateAuthorRequest,
):
    import json

    updates = body.model_dump(exclude_unset=True)

    if not updates:
        return app.utils.responses.error_response(
            code="NO_FIELDS",
            message="No fields provided to update",
            status_code=400,
        )

    proto_fields: typing.Dict[str, typing.Any] = {}
    for field, value in updates.items():
        if field == "remote_ids":
            proto_fields["remote_ids_json"] = json.dumps(value)
        elif field == "alternate_names":
            proto_fields["alternate_names_json"] = json.dumps(value)
        else:
            proto_fields[field] = value

    try:
        async with app.grpc_clients.BooksClient() as client:
            response = await client.update_author(
                author_id=author_id, fields=proto_fields
            )
            author = response.author
            return app.utils.responses.success_response(
                {
                    "author_id": author.author_id,
                    "name": author.name,
                    "slug": author.slug,
                    "bio": author.bio or None,
                    "birth_date": author.birth_date or None,
                    "death_date": author.death_date or None,
                    "birth_place": author.birth_place or None,
                    "nationality": author.nationality or None,
                    "photo_url": author.photo_url or None,
                    "wikidata_id": author.wikidata_id or None,
                    "wikipedia_url": author.wikipedia_url or None,
                    "remote_ids": dict(author.remote_ids),
                    "alternate_names": list(author.alternate_names),
                    "open_library_id": author.open_library_id or None,
                    "updated_at": author.updated_at,
                }
            )
    except grpc.RpcError as e:
        logger.error(f"gRPC error updating author: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update author",
            details={"grpc_code": e.code().name, "grpc_details": e.details()},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error updating author: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )


@router.patch(
    "/series/{series_id}",
    response_model=app.models.books_responses.AdminSeriesUpdateResponse,
    summary="Update a series",
    description="""Partially update a series' editable fields. Only the fields included
    in the request body are changed — omitted fields are left untouched.""",
    dependencies=[
        fastapi.Depends(lambda: limiter),
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Series updated successfully"},
        400: {"description": "No fields provided to update"},
        404: {"description": "Series not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def update_series(
    request: fastapi.Request,
    series_id: int,
    body: app.models.books_responses.AdminUpdateSeriesRequest,
):
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        return app.utils.responses.error_response(
            code="NO_FIELDS",
            message="No fields provided to update",
            status_code=400,
        )

    try:
        async with app.grpc_clients.BooksClient() as client:
            response = await client.update_series(series_id=series_id, fields=updates)
            series = response.series
            return app.utils.responses.success_response(
                {
                    "series_id": series.series_id,
                    "name": series.name,
                    "slug": series.slug,
                    "description": series.description or None,
                    "total_books": series.total_books,
                    "avg_rating": series.avg_rating or None,
                    "rating_count": series.rating_count,
                    "ol_avg_rating": series.ol_avg_rating or None,
                    "ol_rating_count": series.ol_rating_count,
                    "updated_at": series.updated_at,
                }
            )
    except grpc.RpcError as e:
        logger.error(f"gRPC error updating series: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update series",
            details={"grpc_code": e.code().name, "grpc_details": e.details()},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error updating series: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            details={"error": str(e)},
            status_code=500,
        )
