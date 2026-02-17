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
        "updated_at": b.updated_at,
        "book_author_names": list(b.book_author_names),
        "book_author_slugs": list(b.book_author_slugs),
        "book_series_name": b.book_series_name or None,
        "book_series_slug": b.book_series_slug or None
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
        "readability": r.readability if r.has_readability else None,
        "plot_complexity": r.plot_complexity if r.has_plot_complexity else None,
        "humor": r.humor if r.has_humor else None,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "book_author_names": list(r.book_author_names),
        "book_author_slugs": list(r.book_author_slugs),
        "book_series_name": r.book_series_name or None,
        "book_series_slug": r.book_series_slug or None
    }


def _comment_proto_to_dict(c) -> typing.Dict[str, typing.Any]:
    return {
        "comment_id": c.comment_id,
        "user_id": c.user_id,
        "username": c.username,
        "book_id": c.book_id,
        "book_slug": c.book_slug,
        "book_title": c.book_title or None,
        "body": c.body,
        "is_spoiler": c.is_spoiler,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "book_cover_url": c.book_cover_url or None,
        "book_author_names": list(c.book_author_names),
        "book_author_slugs": list(c.book_author_slugs),
        "book_series_name": c.book_series_name or None,
        "book_series_slug": c.book_series_slug or None
    }


# ============================================================
# User Book Info (consolidated)
# ============================================================

@router.get(
    "/users/me/books/{book_slug}",
    response_model=app.models.user_data_responses.UserBookInfoResponse,
    summary="Get all your data for a specific book",
    description="""
    Retrieve the authenticated user's bookshelf entry, rating, and comment
    for a given book in a single call. Each field is `null` if the user has
    no corresponding data for the book.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {"description": "User book info retrieved"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_user_book_info(
    request: fastapi.Request,
    book_slug: str,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.user_data_client.get_user_book_info(
            user_id=current_user["user_id"],
            book_slug=book_slug
        )
        data: typing.Dict[str, typing.Any] = {
            "bookshelf": _bookshelf_proto_to_dict(response.bookshelf)
            if response.HasField("bookshelf") else None,
            "rating": _rating_proto_to_dict(response.rating)
            if response.HasField("rating") else None,
            "comment": _comment_proto_to_dict(response.comment)
            if response.HasField("comment") else None,
        }
        return app.utils.responses.success_response(data)
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_user_book_info: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_user_book_info: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ============================================================
# Bookshelf
# ============================================================

@router.put(
    "/users/me/bookshelves/{book_slug}",
    response_model=app.models.user_data_responses.BookshelfResponse,
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


@router.delete(
    "/users/me/bookshelves/{book_slug}",
    status_code=204,
    summary="Remove a book from your bookshelf",
    description="""
    Permanently remove a book from the authenticated user's bookshelf.
    This also removes the favourite flag if set.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        204: {"description": "Bookshelf entry removed"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book or bookshelf entry not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def delete_bookshelf(
    request: fastapi.Request,
    book_slug: str,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        await app.grpc_clients.user_data_client.delete_bookshelf(
            user_id=current_user["user_id"],
            book_slug=book_slug
        )
        return fastapi.Response(status_code=204)
    except grpc.RpcError as e:
        logger.error(f"gRPC error in delete_bookshelf: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in delete_bookshelf: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


@router.get(
    "/users/me/bookshelves",
    response_model=app.models.user_data_responses.BookshelfListResponse,
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
    response_model=app.models.user_data_responses.BookshelfListResponse,
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


@router.get(
    "/users/{username}/stats",
    response_model=app.models.user_data_responses.ProfileStatsResponse,
    summary="Get a user's profile statistics",
    description="""
    Returns public statistics for any user account: number of books in each
    bookshelf status, favourite books count, ratings count, and comments count.

    This endpoint does not require authentication.
    """,
    responses={
        200: {"description": "Profile stats returned"},
        404: {"description": "User not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_public_profile_stats(
    request: fastapi.Request,
    username: str,
):
    try:
        response = await app.grpc_clients.user_data_client.get_public_profile_stats(
            username=username
        )
        s = response.stats
        return app.utils.responses.success_response({
            "stats": {
                "want_to_read_count": s.want_to_read_count,
                "reading_count": s.reading_count,
                "read_count": s.read_count,
                "abandoned_count": s.abandoned_count,
                "favourites_count": s.favourites_count,
                "ratings_count": s.ratings_count,
                "comments_count": s.comments_count
            }
        })
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_public_profile_stats: {e.code()} - {e.details()}")
        return _grpc_error_response(e)
    except Exception as e:
        logger.error(f"Unexpected error in get_public_profile_stats: {e}")
        return app.utils.responses.error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ============================================================
# Favourites
# ============================================================

@router.post(
    "/books/{book_slug}/favourite",
    response_model=app.models.user_data_responses.FavouriteResponse,
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
    response_model=app.models.user_data_responses.FavouriteResponse,
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
    response_model=app.models.user_data_responses.BookshelfListResponse,
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
    response_model=app.models.user_data_responses.RatingResponse,
    status_code=201,
    summary="Rate a book",
    description="""
    Submit or update a rating for a book. Only `overall_rating` is required (0.5–5.0).
    All sub-dimension ratings are optional (0.5–5.0 each).

    **Quality dimensions** (higher = better): `writing_quality`, `emotional_impact`,
    `intellectual_depth`, `rereadability`.

    **Spectrum dimensions** (labeled endpoints): `pacing` (Slow↔Fast),
    `readability` (Easy↔Challenging), `plot_complexity` (Simple↔Complex),
    `humor` (Serious↔Humorous).

    Rating updates automatically recalculate the book's `avg_rating`, `rating_count`,
    and `sub_rating_stats`.

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
            rereadability=body.rereadability,
            readability=body.readability,
            plot_complexity=body.plot_complexity,
            humor=body.humor
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

    Also recalculates the book's `avg_rating`, `rating_count`, and `sub_rating_stats`.

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
    response_model=app.models.user_data_responses.RatingListResponse,
    summary="Get your ratings",
    description="""
    Retrieve all books the authenticated user has rated.

    **Filtering:** `min_rating`, `max_rating` (0.5–5.0).

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
    min_rating: typing.Optional[float] = fastapi.Query(None, ge=0.5, le=5.0),
    max_rating: typing.Optional[float] = fastapi.Query(None, ge=0.5, le=5.0),
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

@router.post(
    "/books/{book_slug}/comments",
    response_model=app.models.user_data_responses.CommentResponse,
    status_code=201,
    summary="Post a comment on a book",
    description="""
    Create a comment on a book (1–5000 characters). Only one comment per user per book is allowed.
    Use `PUT /books/{book_slug}/comments/{comment_id}` to edit an existing comment.

    Mark `is_spoiler: true` to hide the comment behind a spoiler warning.

    The response includes a `username` field with the commenter's display name.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        201: {"description": "Comment created. Response includes comment_id, user_id, username, body, is_spoiler, created_at, updated_at"},
        401: {"description": "Not authenticated"},
        404: {"description": "Book not found"},
        409: {"description": "Comment already exists for this book"}
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
    response_model=app.models.user_data_responses.CommentResponse,
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
    Permanently delete a comment. Only the comment's author can delete it.

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
    response_model=app.models.user_data_responses.CommentListResponse,
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
