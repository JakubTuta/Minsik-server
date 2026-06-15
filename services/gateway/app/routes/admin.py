import logging
import typing

import json

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


@router.get(
    "/ingestion/coverage",
    response_model=app.models.responses.APIResponse,
    summary="Get data coverage stats",
    description="Returns counts of books/authors/series in the database.",
    dependencies=[
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
        response = await app.grpc_clients.ingestion_client.get_data_coverage()

        data = app.models.requests.DataCoverageResponse(
            db_books_count=response.db_books_count,
            db_authors_count=response.db_authors_count,
            db_series_count=response.db_series_count,
            cached=response.cached,
        )

        return app.utils.responses.success_response(
            data.model_dump(), status_code=200
        )

    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "admin", e)
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to communicate with ingestion service",
            details={"grpc_code": e.code().name},
            status_code=500,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.post(
    "/ingestion/import-dump",
    response_model=app.models.responses.APIResponse,
    summary="Import Open Library data dump",
    description="Trigger an import of Open Library's monthly data dump. Import runs asynchronously in the background; check service logs for progress.",
    dependencies=[
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
        response = await app.grpc_clients.ingestion_client.import_dump()

        data = app.models.requests.ImportDumpResponse(
            status=response.status, message=response.message
        )

        return app.utils.responses.success_response(
            data.model_dump(), status_code=200
        )

    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "admin", e)
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to start dump import",
            details={"grpc_code": e.code().name},
            status_code=500,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.post(
    "/jobs/cleanup",
    response_model=app.models.responses.APIResponse,
    summary="Trigger data cleanup job",
    description="Manually trigger a full data cleanup cycle. Runs asynchronously in the background; check service logs for progress.",
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Cleanup started or already running"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def run_cleanup(request: fastapi.Request):
    try:
        response = await app.grpc_clients.ingestion_client.run_cleanup()

        data = app.models.requests.JobTriggerResponse(
            status=response.status, message=response.message
        )

        return app.utils.responses.success_response(
            data.model_dump(), status_code=200
        )

    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "admin", e)
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to trigger cleanup job",
            details={"grpc_code": e.code().name},
            status_code=500,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.post(
    "/jobs/reindex",
    response_model=app.models.responses.APIResponse,
    summary="Trigger full Elasticsearch reindex",
    description="Manually trigger a full Elasticsearch reindex of all books, authors, and series. Runs asynchronously in the background; check service logs for progress.",
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Reindex started or already running"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def run_reindex(request: fastapi.Request):
    try:
        response = await app.grpc_clients.books_client.trigger_reindex()

        data = app.models.requests.JobTriggerResponse(
            status=response.status, message=response.message
        )

        return app.utils.responses.success_response(
            data.model_dump(), status_code=200
        )

    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "admin", e)
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to trigger reindex",
            details={"grpc_code": e.code().name},
            status_code=500,
        )

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
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
        elif field == "isbn":
            proto_fields["isbn_json"] = json.dumps(value)
        elif field == "external_ids":
            proto_fields["external_ids_json"] = json.dumps(value)
        elif field == "series_position":
            proto_fields["series_position"] = str(value) if value is not None else ""
        elif field == "series_id":
            proto_fields["series_id"] = value if value is not None else 0
        else:
            proto_fields[field] = value

    try:
        response = await app.grpc_clients.books_client.update_book(book_id=book_id, fields=proto_fields)
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
                "series_position": (
                    float(book.series_position) if book.series_position else None
                ),
                "rating_count": book.rating_count,
                "avg_rating": float(book.avg_rating) if book.avg_rating else 0.0,
                "ol_rating_count": book.ol_rating_count,
                "ol_avg_rating": (
                    float(book.ol_avg_rating) if book.ol_avg_rating else 0.0
                ),
                "updated_at": book.updated_at,
            }
        )
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "updating book", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update book",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error updating book: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.patch(
    "/authors/{author_id}",
    response_model=app.models.books_responses.AdminAuthorUpdateResponse,
    summary="Update an author",
    description="""Partially update an author's editable fields. Only the fields included
    in the request body are changed — omitted fields are left untouched.""",
    dependencies=[
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
        response = await app.grpc_clients.books_client.update_author(
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
        app.utils.responses.log_grpc_error(logger, "updating author", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update author",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error updating author: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.patch(
    "/series/{series_id}",
    response_model=app.models.books_responses.AdminSeriesUpdateResponse,
    summary="Update a series",
    description="""Partially update a series' editable fields. Only the fields included
    in the request body are changed — omitted fields are left untouched.""",
    dependencies=[
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
        response = await app.grpc_clients.books_client.update_series(series_id=series_id, fields=updates)
        series = response.series
        return app.utils.responses.success_response(
            {
                "series_id": series.series_id,
                "name": series.name,
                "slug": series.slug,
                "description": series.description or None,
                "total_books": series.total_books,
                "avg_rating": (
                    float(series.avg_rating) if series.avg_rating else 0.0
                ),
                "rating_count": series.rating_count,
                "ol_avg_rating": (
                    float(series.ol_avg_rating) if series.ol_avg_rating else 0.0
                ),
                "ol_rating_count": series.ol_rating_count,
                "updated_at": series.updated_at,
            }
        )
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "updating series", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update series",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error updating series: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.delete(
    "/books/{book_id}/authors/{author_id}",
    response_model=app.models.responses.APIResponse,
    summary="Remove an author from a book",
    description="Remove the author-book association. Neither the book nor the author is deleted.",
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Author removed from book"},
        404: {"description": "Book or author-book association not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def remove_book_author(request: fastapi.Request, book_id: int, author_id: int):
    try:
        response = await app.grpc_clients.books_client.remove_book_author(
            book_id=book_id, author_id=author_id
        )
        book = response.book
        return app.utils.responses.success_response(
            {
                "book_id": book.book_id,
                "title": book.title,
                "authors": [
                    {"author_id": a.author_id, "name": a.name, "slug": a.slug}
                    for a in book.authors
                ],
            }
        )
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "removing book author", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to remove author from book",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error removing book author: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.delete(
    "/series/{series_id}/authors/{author_id}",
    response_model=app.models.responses.APIResponse,
    summary="Remove an author from a series",
    description="Remove the author from all books belonging to the series. Neither the series, the books, nor the author is deleted.",
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Author removed from series books"},
        404: {"description": "Series or author not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def remove_series_author(request: fastapi.Request, series_id: int, author_id: int):
    try:
        await app.grpc_clients.books_client.remove_series_author(
            series_id=series_id, author_id=author_id
        )
        return app.utils.responses.success_response(
            {"series_id": series_id, "removed_author_id": author_id}
        )
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "removing series author", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to remove author from series",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error removing series author: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.delete(
    "/books/{book_id}",
    response_model=app.models.responses.APIResponse,
    summary="Delete a book",
    description=(
        "Permanently delete a book and all associated data: book_authors, book_genres, "
        "user bookshelves, ratings, and comments. User stats are recalculated for all "
        "affected users."
    ),
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Book deleted successfully"},
        404: {"description": "Book not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def delete_book(request: fastapi.Request, book_id: int):
    try:
        response = await app.grpc_clients.books_client.delete_book(book_id=book_id)
        return app.utils.responses.success_response({"message": response.message})
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "deleting book", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to delete book",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting book: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.delete(
    "/authors/{author_id}",
    response_model=app.models.responses.APIResponse,
    summary="Delete an author",
    description=(
        "Permanently delete an author and their book_authors join entries. "
        "Books written by this author are NOT deleted."
    ),
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Author deleted successfully"},
        404: {"description": "Author not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def delete_author(request: fastapi.Request, author_id: int):
    try:
        response = await app.grpc_clients.books_client.delete_author(author_id=author_id)
        return app.utils.responses.success_response({"message": response.message})
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "deleting author", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to delete author",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting author: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )


@router.delete(
    "/series/{series_id}",
    response_model=app.models.responses.APIResponse,
    summary="Delete a series",
    description=(
        "Permanently delete a series. Books that belong to the series have their "
        "series_id and series_position set to NULL — they are NOT deleted."
    ),
    dependencies=[
        fastapi.Depends(app.middleware.auth.require_admin),
    ],
    responses={
        200: {"description": "Series deleted successfully"},
        404: {"description": "Series not found"},
        **_AUTH_RESPONSES,
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def delete_series(request: fastapi.Request, series_id: int):
    try:
        response = await app.grpc_clients.books_client.delete_series(series_id=series_id)
        return app.utils.responses.success_response({"message": response.message})
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "deleting series", e)
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND", message=e.details(), status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to delete series",
            details={"grpc_code": e.code().name},
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting series: {str(e)}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        )
