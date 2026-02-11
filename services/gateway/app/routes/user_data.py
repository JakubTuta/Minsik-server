import typing
import fastapi
import grpc
import logging
import app.config
import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit
import app.models.user_data_responses
import app.utils.responses

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(prefix="/api/v1", tags=["User Data"])

limiter = app.middleware.rate_limit.limiter


def _grpc_error_response(e: grpc.RpcError) -> fastapi.responses.JSONResponse:
    code = e.code()
    if code == grpc.StatusCode.NOT_FOUND:
        return app.utils.responses.error_response("NOT_FOUND", e.details(), status_code=404)
    if code == grpc.StatusCode.PERMISSION_DENIED:
        return app.utils.responses.error_response("PERMISSION_DENIED", e.details(), status_code=403)
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return app.utils.responses.error_response("INVALID_ARGUMENT", e.details(), status_code=400)
    if code == grpc.StatusCode.ALREADY_EXISTS:
        return app.utils.responses.error_response("ALREADY_EXISTS", e.details(), status_code=409)
    return app.utils.responses.error_response("INTERNAL_ERROR", "An internal error occurred", status_code=500)


def _bookshelf_proto_to_dict(b) -> typing.Dict[str, typing.Any]:
    return {
        "bookshelf_id": b.bookshelf_id,
        "user_id": b.user_id,
        "book_id": b.book_id,
        "book_slug": b.book_slug,
        "book_title": b.book_title,
        "book_cover_url": b.book_cover_url,
        "status": b.status,
        "is_favorite": b.is_favorite,
        "created_at": b.created_at,
        "updated_at": b.updated_at
    }


def _rating_proto_to_dict(r) -> typing.Dict[str, typing.Any]:
    return {
        "rating_id": r.rating_id,
        "user_id": r.user_id,
        "book_id": r.book_id,
        "book_slug": r.book_slug,
        "book_title": r.book_title,
        "book_cover_url": r.book_cover_url,
        "overall_rating": r.overall_rating,
        "review_text": r.review_text or None,
        "pacing": r.pacing if r.has_pacing else None,
        "emotional_impact": r.emotional_impact if r.has_emotional_impact else None,
        "intellectual_depth": r.intellectual_depth if r.has_intellectual_depth else None,
        "writing_quality": r.writing_quality if r.has_writing_quality else None,
        "rereadability": r.rereadability if r.has_rereadability else None,
        "created_at": r.created_at,
        "updated_at": r.updated_at
    }


def _comment_proto_to_dict(c) -> typing.Dict[str, typing.Any]:
    return {
        "comment_id": c.comment_id,
        "user_id": c.user_id,
        "book_id": c.book_id,
        "book_slug": c.book_slug,
        "body": c.body,
        "is_spoiler": c.is_spoiler,
        "created_at": c.created_at,
        "updated_at": c.updated_at
    }


def _note_proto_to_dict(n) -> typing.Dict[str, typing.Any]:
    return {
        "note_id": n.note_id,
        "user_id": n.user_id,
        "book_id": n.book_id,
        "book_slug": n.book_slug,
        "note_text": n.note_text,
        "page_number": n.page_number if n.has_page_number else None,
        "is_spoiler": n.is_spoiler,
        "created_at": n.created_at,
        "updated_at": n.updated_at
    }


# ============================================================
# Bookshelf
# ============================================================

@router.put(
    "/users/me/bookshelves/{book_slug}",
    summary="Add or update a book on your bookshelf",
    description="""
    Set the reading status for a book on the authenticated user's bookshelf.

    Valid statuses: `want_to_read`, `reading`, `read`, `abandoned`.

    Creates the entry if it does not exist, updates it otherwise.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Bookshelf entry updated"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def upsert_bookshelf(
    request: fastapi.Request,
    book_slug: str,
    body: app.models.user_data_responses.UpsertBookshelfRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.upsert_bookshelf(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            status=body.status
        )
        return app.utils.responses.success_response(
            {"bookshelf": _bookshelf_proto_to_dict(response.bookshelf)},
            status_code=200
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in upsert_bookshelf: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in upsert_bookshelf: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/me/bookshelves",
    summary="Get your bookshelf",
    description="""
    Retrieve the authenticated user's bookshelf entries with optional filtering and sorting.

    **Filtering:** `status` (one of `want_to_read`, `reading`, `read`, `abandoned`), `favourites_only`.

    **Sorting:** `sort_by` (`created_at`, `updated_at`, `book_title`), `order` (`asc`, `desc`).

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Bookshelf retrieved"},
        401: {"description": "Not authenticated"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_user_bookshelves(
    request: fastapi.Request,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    status: typing.Optional[typing.Literal["want_to_read", "reading", "read", "abandoned"]] = fastapi.Query(None),
    favourites_only: bool = fastapi.Query(False),
    sort_by: typing.Literal["created_at", "updated_at", "book_title"] = fastapi.Query("created_at"),
    order: typing.Literal["asc", "desc"] = fastapi.Query("desc"),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_user_bookshelves(
            user_id=current_user["user_id"],
            limit=limit,
            offset=offset,
            status_filter=status or "",
            favourites_only=favourites_only,
            sort_by=sort_by,
            order=order
        )
        items = [_bookshelf_proto_to_dict(b) for b in response.bookshelves]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_user_bookshelves: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_user_bookshelves: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/{username}/bookshelves",
    summary="Get a user's public bookshelf",
    description="""
    Retrieve any user's bookshelf by their username.

    **Filtering:** `status` (one of `want_to_read`, `reading`, `read`, `abandoned`), `favourites_only`.

    **Sorting:** `sort_by` (`created_at`, `updated_at`, `book_title`), `order` (`asc`, `desc`).

    No authentication required — accessible by anyone including guests.
    """,
    responses={
        200: {"description": "Bookshelf retrieved"},
        404: {"description": "User not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_public_bookshelves(
    request: fastapi.Request,
    username: str,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    status: typing.Optional[typing.Literal["want_to_read", "reading", "read", "abandoned"]] = fastapi.Query(None),
    favourites_only: bool = fastapi.Query(False),
    sort_by: typing.Literal["created_at", "updated_at", "book_title"] = fastapi.Query("created_at"),
    order: typing.Literal["asc", "desc"] = fastapi.Query("desc"),
):
    try:
        response = await app.grpc_clients.user_data_client.get_public_bookshelves(
            username=username,
            limit=limit,
            offset=offset,
            status_filter=status or "",
            favourites_only=favourites_only,
            sort_by=sort_by,
            order=order
        )
        items = [_bookshelf_proto_to_dict(b) for b in response.bookshelves]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_public_bookshelves: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_public_bookshelves: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ============================================================
# Favourites
# ============================================================

@router.post(
    "/books/{book_slug}/favourite",
    summary="Add a book to favourites",
    description="""
    Mark a book as a favourite. Creates a bookshelf entry with `want_to_read` status if one doesn't exist.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Book marked as favourite"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def add_favourite(
    request: fastapi.Request,
    book_slug: str,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.toggle_favourite(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            is_favorite=True
        )
        return app.utils.responses.success_response(
            {"is_favorite": response.is_favorite, "book_id": response.book_id, "book_slug": response.book_slug}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in add_favourite: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in add_favourite: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.delete(
    "/books/{book_slug}/favourite",
    summary="Remove a book from favourites",
    description="""
    Unmark a book as a favourite. The bookshelf entry status is preserved.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Book removed from favourites"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def remove_favourite(
    request: fastapi.Request,
    book_slug: str,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.toggle_favourite(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            is_favorite=False
        )
        return app.utils.responses.success_response(
            {"is_favorite": response.is_favorite, "book_id": response.book_id, "book_slug": response.book_slug}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in remove_favourite: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in remove_favourite: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/me/favourites",
    summary="Get your favourite books",
    description="""
    Retrieve all books the authenticated user has marked as favourites.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Favourites retrieved"},
        401: {"description": "Not authenticated"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_user_favourites(
    request: fastapi.Request,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_user_favourites(
            user_id=current_user["user_id"],
            limit=limit,
            offset=offset
        )
        items = [_bookshelf_proto_to_dict(b) for b in response.bookshelves]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_user_favourites: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_user_favourites: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ============================================================
# Ratings
# ============================================================

@router.post(
    "/books/{book_slug}/rate",
    summary="Rate a book",
    description="""
    Submit or update a rating for a book. Only `overall_rating` is required (1.0–5.0).
    All sub-dimension ratings are optional.

    Rating updates automatically recalculate the book's `avg_rating` and `rating_count`.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        201: {"description": "Rating submitted"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def upsert_rating(
    request: fastapi.Request,
    book_slug: str,
    body: app.models.user_data_responses.UpsertRatingRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.upsert_rating(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            overall_rating=body.overall_rating,
            review_text=body.review_text or "",
            pacing=body.pacing,
            emotional_impact=body.emotional_impact,
            intellectual_depth=body.intellectual_depth,
            writing_quality=body.writing_quality,
            rereadability=body.rereadability
        )
        return app.utils.responses.success_response(
            {"rating": _rating_proto_to_dict(response.rating)},
            status_code=201
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in upsert_rating: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in upsert_rating: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.delete(
    "/books/{book_slug}/rate",
    status_code=204,
    summary="Delete your rating for a book",
    description="""
    Remove the authenticated user's rating for a book.

    Also recalculates the book's `avg_rating` and `rating_count`.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        204: {"description": "Rating deleted"},
        401: {"description": "Not authenticated"},
        404: {"description": "Rating not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def delete_rating(
    request: fastapi.Request,
    book_slug: str,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        await app.grpc_clients.user_data_client.delete_rating(
            user_id=current_user["user_id"],
            book_slug=book_slug
        )
        return fastapi.Response(status_code=204)
    except grpc.RpcError as e:
        logger.error(f"gRPC error in delete_rating: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in delete_rating: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/me/ratings",
    summary="Get your ratings",
    description="""
    Retrieve all books the authenticated user has rated.

    **Filtering:** `min_rating`, `max_rating` (1.0–5.0).

    **Sorting:** `sort_by` (`created_at`, `overall_rating`), `order` (`asc`, `desc`).

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Ratings retrieved"},
        401: {"description": "Not authenticated"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_user_ratings(
    request: fastapi.Request,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    sort_by: typing.Literal["created_at", "overall_rating"] = fastapi.Query("created_at"),
    order: typing.Literal["asc", "desc"] = fastapi.Query("desc"),
    min_rating: typing.Optional[float] = fastapi.Query(None, ge=1.0, le=5.0),
    max_rating: typing.Optional[float] = fastapi.Query(None, ge=1.0, le=5.0),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_user_ratings(
            user_id=current_user["user_id"],
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            min_rating=min_rating or 0.0,
            max_rating=max_rating or 0.0
        )
        items = [_rating_proto_to_dict(r) for r in response.ratings]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_user_ratings: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_user_ratings: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ============================================================
# Comments
# ============================================================

@router.get(
    "/books/{book_slug}/comments",
    summary="Get comments for a book",
    description="""
    Retrieve comments for a book. **Public endpoint — no authentication required.**

    Spoilers are hidden by default; set `include_spoilers=true` to show them.

    **Sorting:** `order` (`desc` for newest first, `asc` for oldest first).
    """,
    responses={
        200: {"description": "Comments retrieved"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_book_comments(
    request: fastapi.Request,
    book_slug: str,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    order: typing.Literal["asc", "desc"] = fastapi.Query("desc"),
    include_spoilers: bool = fastapi.Query(False)
):
    try:
        response = await app.grpc_clients.user_data_client.get_book_comments(
            book_slug=book_slug,
            limit=limit,
            offset=offset,
            order=order,
            include_spoilers=include_spoilers
        )
        items = [_comment_proto_to_dict(c) for c in response.comments]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_book_comments: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_book_comments: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.post(
    "/books/{book_slug}/comments",
    summary="Post a comment on a book",
    description="""
    Create a new comment on a book (1–5000 characters).

    Mark `is_spoiler: true` to hide the comment behind a spoiler warning.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        201: {"description": "Comment created"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def create_comment(
    request: fastapi.Request,
    book_slug: str,
    body: app.models.user_data_responses.CreateCommentRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.create_comment(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            body=body.body,
            is_spoiler=body.is_spoiler
        )
        return app.utils.responses.success_response(
            {"comment": _comment_proto_to_dict(response.comment)},
            status_code=201
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in create_comment: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in create_comment: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.put(
    "/books/{book_slug}/comments/{comment_id}",
    summary="Update a comment",
    description="""
    Edit the body or spoiler flag of an existing comment. Only the comment's author can update it.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Comment updated"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not the comment owner"},
        404: {"description": "Comment not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def update_comment(
    request: fastapi.Request,
    book_slug: str,
    comment_id: int,
    body: app.models.user_data_responses.UpdateCommentRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.update_comment(
            comment_id=comment_id,
            user_id=current_user["user_id"],
            body=body.body,
            is_spoiler=body.is_spoiler
        )
        return app.utils.responses.success_response(
            {"comment": _comment_proto_to_dict(response.comment)}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in update_comment: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in update_comment: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.delete(
    "/books/{book_slug}/comments/{comment_id}",
    status_code=204,
    summary="Delete a comment",
    description="""
    Soft-delete a comment (the record is retained in the database but hidden from all responses).
    Only the comment's author can delete it.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        204: {"description": "Comment deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not the comment owner"},
        404: {"description": "Comment not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def delete_comment(
    request: fastapi.Request,
    book_slug: str,
    comment_id: int,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        await app.grpc_clients.user_data_client.delete_comment(
            comment_id=comment_id,
            user_id=current_user["user_id"]
        )
        return fastapi.Response(status_code=204)
    except grpc.RpcError as e:
        logger.error(f"gRPC error in delete_comment: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in delete_comment: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/me/comments",
    summary="Get your comments",
    description="""
    Retrieve all comments posted by the authenticated user.

    **Filtering:** `book_slug` to limit to a specific book.

    **Sorting:** `sort_by` (`created_at`, `updated_at`), `order` (`asc`, `desc`).

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Comments retrieved"},
        401: {"description": "Not authenticated"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_user_comments(
    request: fastapi.Request,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    sort_by: typing.Literal["created_at", "updated_at"] = fastapi.Query("created_at"),
    order: typing.Literal["asc", "desc"] = fastapi.Query("desc"),
    book_slug: typing.Optional[str] = fastapi.Query(None),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_user_comments(
            user_id=current_user["user_id"],
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            book_slug=book_slug or ""
        )
        items = [_comment_proto_to_dict(c) for c in response.comments]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_user_comments: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_user_comments: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ============================================================
# Notes
# ============================================================

@router.get(
    "/books/{book_slug}/notes",
    summary="Get your notes for a book",
    description="""
    Retrieve all notes the authenticated user has created for a specific book.

    **Sorting:** `sort_by` (`page_number` sorts by page ascending with NULLs last, `created_at`), `order` (`asc`, `desc`).

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Notes retrieved"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_book_notes(
    request: fastapi.Request,
    book_slug: str,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    sort_by: typing.Literal["page_number", "created_at"] = fastapi.Query("page_number"),
    order: typing.Literal["asc", "desc"] = fastapi.Query("asc"),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_book_notes(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order
        )
        items = [_note_proto_to_dict(n) for n in response.notes]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_book_notes: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_book_notes: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.post(
    "/books/{book_slug}/notes",
    summary="Create a note for a book",
    description="""
    Create a personal note for a book (1–10000 characters). Optionally include a page number.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        201: {"description": "Note created"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def create_note(
    request: fastapi.Request,
    book_slug: str,
    body: app.models.user_data_responses.CreateNoteRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.create_note(
            user_id=current_user["user_id"],
            book_slug=book_slug,
            note_text=body.note_text,
            page_number=body.page_number,
            is_spoiler=body.is_spoiler
        )
        return app.utils.responses.success_response(
            {"note": _note_proto_to_dict(response.note)},
            status_code=201
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in create_note: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in create_note: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.put(
    "/books/{book_slug}/notes/{note_id}",
    summary="Update a note",
    description="""
    Edit the text, page number, or spoiler flag of a note. Only the note's author can update it.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Note updated"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not the note owner"},
        404: {"description": "Note not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def update_note(
    request: fastapi.Request,
    book_slug: str,
    note_id: int,
    body: app.models.user_data_responses.UpdateNoteRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.update_note(
            note_id=note_id,
            user_id=current_user["user_id"],
            note_text=body.note_text,
            page_number=body.page_number,
            is_spoiler=body.is_spoiler
        )
        return app.utils.responses.success_response(
            {"note": _note_proto_to_dict(response.note)}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in update_note: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in update_note: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.delete(
    "/books/{book_slug}/notes/{note_id}",
    status_code=204,
    summary="Delete a note",
    description="""
    Permanently delete a note. Only the note's author can delete it.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        204: {"description": "Note deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not the note owner"},
        404: {"description": "Note not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def delete_note(
    request: fastapi.Request,
    book_slug: str,
    note_id: int,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        await app.grpc_clients.user_data_client.delete_note(
            note_id=note_id,
            user_id=current_user["user_id"]
        )
        return fastapi.Response(status_code=204)
    except grpc.RpcError as e:
        logger.error(f"gRPC error in delete_note: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in delete_note: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/me/notes",
    summary="Get all your notes",
    description="""
    Retrieve all notes the authenticated user has created across all books.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "Notes retrieved"},
        401: {"description": "Not authenticated"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_user_notes(
    request: fastapi.Request,
    limit: int = fastapi.Query(10, ge=1, le=100),
    offset: int = fastapi.Query(0, ge=0),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_user_notes(
            user_id=current_user["user_id"],
            limit=limit,
            offset=offset
        )
        items = [_note_proto_to_dict(n) for n in response.notes]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count, "limit": limit, "offset": offset}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_user_notes: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_user_notes: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)
