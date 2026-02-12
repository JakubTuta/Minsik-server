import typing
import logging
import time
import asyncio
import grpc
import sqlalchemy
import app.database
import app.proto.user_data_pb2
import app.proto.user_data_pb2_grpc
import app.services.bookshelf_service
import app.services.rating_service
import app.services.comment_service

logger = logging.getLogger(__name__)

_NOT_FOUND_ERRORS = {"not_found", "book_not_found", "user_not_found"}
_PERMISSION_ERRORS = {"not_owner"}
_ALREADY_EXISTS_ERRORS = {"already_exists"}

_VALID_SORT_COLS: typing.Dict[str, str] = {
    "created_at": "c.created_at",
    "overall_rating": "r.overall_rating",
    "pacing": "r.pacing",
    "emotional_impact": "r.emotional_impact",
    "intellectual_depth": "r.intellectual_depth",
    "writing_quality": "r.writing_quality",
    "rereadability": "r.rereadability",
    "readability": "r.readability",
    "plot_complexity": "r.plot_complexity",
    "humor": "r.humor",
}


class _TtlCache:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self._ttl = ttl_seconds
        self._store: typing.Dict[str, typing.Tuple[float, typing.Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> typing.Optional[typing.Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: typing.Any) -> None:
        async with self._lock:
            self._store[key] = (time.monotonic(), value)

    async def invalidate_by_book(self, book_id: int) -> None:
        prefix = f"{book_id}:"
        async with self._lock:
            for k in [k for k in self._store if k.startswith(prefix)]:
                del self._store[k]


_book_comments_cache = _TtlCache(ttl_seconds=120)


async def _resolve_user(
    session,
    username: str
) -> int:
    result = await session.execute(sqlalchemy.text(
        "SELECT user_id FROM auth.users WHERE username = :username AND is_active = TRUE"
    ), {"username": username})
    row = result.fetchone()
    if row is None:
        raise ValueError("user_not_found")
    return row.user_id


async def _resolve_book(
    session,
    book_slug: str
) -> typing.Tuple[int, str, str]:
    result = await session.execute(sqlalchemy.text(
        "SELECT book_id, title, primary_cover_url FROM books.books WHERE slug = :slug"
    ), {"slug": book_slug})
    row = result.fetchone()
    if row is None:
        raise ValueError("book_not_found")
    return row.book_id, row.title or "", row.primary_cover_url or ""


def _bookshelf_to_proto(
    bookshelf,
    book_slug: str = "",
    book_title: str = "",
    book_cover_url: str = ""
) -> app.proto.user_data_pb2.Bookshelf:
    return app.proto.user_data_pb2.Bookshelf(
        bookshelf_id=bookshelf.bookshelf_id,
        user_id=bookshelf.user_id,
        book_id=bookshelf.book_id,
        book_slug=book_slug,
        book_title=book_title,
        book_cover_url=book_cover_url,
        status=bookshelf.status,
        is_favorite=bookshelf.is_favorite,
        created_at=bookshelf.created_at.isoformat() if bookshelf.created_at else "",
        updated_at=bookshelf.updated_at.isoformat() if bookshelf.updated_at else ""
    )


def _rating_to_proto(
    rating,
    book_slug: str = "",
    book_title: str = "",
    book_cover_url: str = ""
) -> app.proto.user_data_pb2.Rating:
    return app.proto.user_data_pb2.Rating(
        rating_id=rating.rating_id,
        user_id=rating.user_id,
        book_id=rating.book_id,
        book_slug=book_slug,
        book_title=book_title,
        book_cover_url=book_cover_url,
        overall_rating=float(rating.overall_rating),
        review_text=rating.review_text or "",
        pacing=float(rating.pacing) if rating.pacing is not None else 0.0,
        has_pacing=rating.pacing is not None,
        emotional_impact=float(rating.emotional_impact) if rating.emotional_impact is not None else 0.0,
        has_emotional_impact=rating.emotional_impact is not None,
        intellectual_depth=float(rating.intellectual_depth) if rating.intellectual_depth is not None else 0.0,
        has_intellectual_depth=rating.intellectual_depth is not None,
        writing_quality=float(rating.writing_quality) if rating.writing_quality is not None else 0.0,
        has_writing_quality=rating.writing_quality is not None,
        rereadability=float(rating.rereadability) if rating.rereadability is not None else 0.0,
        has_rereadability=rating.rereadability is not None,
        readability=float(rating.readability) if rating.readability is not None else 0.0,
        has_readability=rating.readability is not None,
        plot_complexity=float(rating.plot_complexity) if rating.plot_complexity is not None else 0.0,
        has_plot_complexity=rating.plot_complexity is not None,
        humor=float(rating.humor) if rating.humor is not None else 0.0,
        has_humor=rating.humor is not None,
        created_at=rating.created_at.isoformat() if rating.created_at else "",
        updated_at=rating.updated_at.isoformat() if rating.updated_at else ""
    )


def _comment_to_proto(
    comment,
    book_slug: str = ""
) -> app.proto.user_data_pb2.Comment:
    return app.proto.user_data_pb2.Comment(
        comment_id=comment.comment_id,
        user_id=comment.user_id,
        book_id=comment.book_id,
        book_slug=book_slug,
        body=comment.body,
        is_spoiler=comment.is_spoiler,
        created_at=comment.created_at.isoformat() if comment.created_at else "",
        updated_at=comment.updated_at.isoformat() if comment.updated_at else ""
    )


def _row_to_comment_with_rating(
    row,
    book_slug: str
) -> app.proto.user_data_pb2.BookCommentWithRating:
    has_rating = row.overall_rating is not None
    return app.proto.user_data_pb2.BookCommentWithRating(
        comment_id=row.comment_id,
        user_id=row.user_id,
        book_id=row.book_id,
        book_slug=book_slug,
        body=row.body,
        is_spoiler=row.is_spoiler,
        comment_created_at=row.created_at.isoformat() if row.created_at else "",
        comment_updated_at=row.updated_at.isoformat() if row.updated_at else "",
        has_rating=has_rating,
        overall_rating=float(row.overall_rating) if has_rating else 0.0,
        review_text=row.review_text or "" if has_rating else "",
        pacing=float(row.pacing) if row.pacing is not None else 0.0,
        has_pacing=row.pacing is not None,
        emotional_impact=float(row.emotional_impact) if row.emotional_impact is not None else 0.0,
        has_emotional_impact=row.emotional_impact is not None,
        intellectual_depth=float(row.intellectual_depth) if row.intellectual_depth is not None else 0.0,
        has_intellectual_depth=row.intellectual_depth is not None,
        writing_quality=float(row.writing_quality) if row.writing_quality is not None else 0.0,
        has_writing_quality=row.writing_quality is not None,
        rereadability=float(row.rereadability) if row.rereadability is not None else 0.0,
        has_rereadability=row.rereadability is not None,
        readability=float(row.readability) if row.readability is not None else 0.0,
        has_readability=row.readability is not None,
        plot_complexity=float(row.plot_complexity) if row.plot_complexity is not None else 0.0,
        has_plot_complexity=row.plot_complexity is not None,
        humor=float(row.humor) if row.humor is not None else 0.0,
        has_humor=row.humor is not None,
    )


async def _handle_error(error: Exception, context: grpc.aio.ServicerContext) -> None:
    error_key = str(error)
    if error_key in _NOT_FOUND_ERRORS:
        await context.abort(grpc.StatusCode.NOT_FOUND, f"Resource not found: {error_key}")
    elif error_key in _PERMISSION_ERRORS:
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, f"Permission denied: {error_key}")
    elif error_key in _ALREADY_EXISTS_ERRORS:
        await context.abort(grpc.StatusCode.ALREADY_EXISTS, f"Resource already exists: {error_key}")
    else:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid argument: {error_key}")


class UserDataServicer(app.proto.user_data_pb2_grpc.UserDataServiceServicer):

    async def GetBookshelf(
        self,
        request: app.proto.user_data_pb2.GetBookshelfRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.BookshelfResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, book_title, book_cover_url = await _resolve_book(session, request.book_slug)
                bookshelf = await app.services.bookshelf_service.get_bookshelf(
                    session, request.user_id, book_id
                )
                return app.proto.user_data_pb2.BookshelfResponse(
                    bookshelf=_bookshelf_to_proto(bookshelf, request.book_slug, book_title, book_cover_url)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookshelf: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpsertBookshelf(
        self,
        request: app.proto.user_data_pb2.UpsertBookshelfRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.BookshelfResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, book_title, book_cover_url = await _resolve_book(session, request.book_slug)
                bookshelf = await app.services.bookshelf_service.upsert_bookshelf(
                    session, request.user_id, book_id, request.status
                )
                return app.proto.user_data_pb2.BookshelfResponse(
                    bookshelf=_bookshelf_to_proto(bookshelf, request.book_slug, book_title, book_cover_url)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpsertBookshelf: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteBookshelf(
        self,
        request: app.proto.user_data_pb2.DeleteBookshelfRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                await app.services.bookshelf_service.delete_bookshelf(
                    session, request.user_id, book_id
                )
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteBookshelf: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserBookshelves(
        self,
        request: app.proto.user_data_pb2.GetUserBookshelvesRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        try:
            async with app.database.async_session_maker() as session:
                rows, total_count = await app.services.bookshelf_service.get_user_bookshelves(
                    session,
                    request.user_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.status_filter,
                    request.favourites_only,
                    request.sort_by or "created_at",
                    request.order or "desc"
                )

                slug_map = await _build_book_slug_map(session, [r.book_id for r in rows])
                title_map = await _build_book_title_map(session, [r.book_id for r in rows])
                cover_map = await _build_book_cover_map(session, [r.book_id for r in rows])

                protos = [
                    _bookshelf_to_proto(
                        r,
                        slug_map.get(r.book_id, ""),
                        title_map.get(r.book_id, ""),
                        cover_map.get(r.book_id, "")
                    )
                    for r in rows
                ]
                return app.proto.user_data_pb2.BookshelvesListResponse(
                    bookshelves=protos,
                    total_count=total_count
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserBookshelves: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetPublicBookshelves(
        self,
        request: app.proto.user_data_pb2.GetPublicBookshelvesRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        try:
            async with app.database.async_session_maker() as session:
                user_id = await _resolve_user(session, request.username)
                rows, total_count = await app.services.bookshelf_service.get_user_bookshelves(
                    session,
                    user_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.status_filter,
                    request.favourites_only,
                    request.sort_by or "created_at",
                    request.order or "desc"
                )
                slug_map = await _build_book_slug_map(session, [r.book_id for r in rows])
                title_map = await _build_book_title_map(session, [r.book_id for r in rows])
                cover_map = await _build_book_cover_map(session, [r.book_id for r in rows])
                protos = [
                    _bookshelf_to_proto(
                        r,
                        slug_map.get(r.book_id, ""),
                        title_map.get(r.book_id, ""),
                        cover_map.get(r.book_id, "")
                    )
                    for r in rows
                ]
                return app.proto.user_data_pb2.BookshelvesListResponse(
                    bookshelves=protos,
                    total_count=total_count
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetPublicBookshelves: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetRating(
        self,
        request: app.proto.user_data_pb2.GetRatingRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.RatingResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, book_title, book_cover_url = await _resolve_book(session, request.book_slug)
                rating = await app.services.rating_service.get_rating(
                    session, request.user_id, book_id
                )
                return app.proto.user_data_pb2.RatingResponse(
                    rating=_rating_to_proto(rating, request.book_slug, book_title, book_cover_url)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetRating: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpsertRating(
        self,
        request: app.proto.user_data_pb2.UpsertRatingRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.RatingResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, book_title, book_cover_url = await _resolve_book(session, request.book_slug)

                sub_ratings: typing.Dict[str, float] = {}
                if request.has_pacing:
                    sub_ratings["pacing"] = request.pacing
                if request.has_emotional_impact:
                    sub_ratings["emotional_impact"] = request.emotional_impact
                if request.has_intellectual_depth:
                    sub_ratings["intellectual_depth"] = request.intellectual_depth
                if request.has_writing_quality:
                    sub_ratings["writing_quality"] = request.writing_quality
                if request.has_rereadability:
                    sub_ratings["rereadability"] = request.rereadability
                if request.has_readability:
                    sub_ratings["readability"] = request.readability
                if request.has_plot_complexity:
                    sub_ratings["plot_complexity"] = request.plot_complexity
                if request.has_humor:
                    sub_ratings["humor"] = request.humor

                rating = await app.services.rating_service.upsert_rating(
                    session,
                    request.user_id,
                    book_id,
                    request.overall_rating,
                    sub_ratings,
                    request.review_text or None
                )
                return app.proto.user_data_pb2.RatingResponse(
                    rating=_rating_to_proto(rating, request.book_slug, book_title, book_cover_url)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpsertRating: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteRating(
        self,
        request: app.proto.user_data_pb2.DeleteRatingRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                await app.services.rating_service.delete_rating(
                    session, request.user_id, book_id
                )
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteRating: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserRatings(
        self,
        request: app.proto.user_data_pb2.GetUserRatingsRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.RatingsListResponse:
        try:
            async with app.database.async_session_maker() as session:
                rows, total_count = await app.services.rating_service.get_user_ratings(
                    session,
                    request.user_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.sort_by or "created_at",
                    request.order or "desc",
                    request.min_rating,
                    request.max_rating
                )

                slug_map = await _build_book_slug_map(session, [r.book_id for r in rows])
                title_map = await _build_book_title_map(session, [r.book_id for r in rows])
                cover_map = await _build_book_cover_map(session, [r.book_id for r in rows])

                protos = [
                    _rating_to_proto(
                        r,
                        slug_map.get(r.book_id, ""),
                        title_map.get(r.book_id, ""),
                        cover_map.get(r.book_id, "")
                    )
                    for r in rows
                ]
                return app.proto.user_data_pb2.RatingsListResponse(
                    ratings=protos,
                    total_count=total_count
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserRatings: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def ToggleFavourite(
        self,
        request: app.proto.user_data_pb2.ToggleFavouriteRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.FavouriteResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                bookshelf = await app.services.bookshelf_service.toggle_favourite(
                    session, request.user_id, book_id, request.is_favorite
                )
                return app.proto.user_data_pb2.FavouriteResponse(
                    is_favorite=bookshelf.is_favorite,
                    book_id=bookshelf.book_id,
                    book_slug=request.book_slug
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in ToggleFavourite: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserFavourites(
        self,
        request: app.proto.user_data_pb2.GetUserFavouritesRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        try:
            async with app.database.async_session_maker() as session:
                rows, total_count = await app.services.bookshelf_service.get_user_bookshelves(
                    session,
                    request.user_id,
                    request.limit or 10,
                    request.offset or 0,
                    status_filter="",
                    favourites_only=True,
                    sort_by="created_at",
                    order="desc"
                )

                slug_map = await _build_book_slug_map(session, [r.book_id for r in rows])
                title_map = await _build_book_title_map(session, [r.book_id for r in rows])
                cover_map = await _build_book_cover_map(session, [r.book_id for r in rows])

                protos = [
                    _bookshelf_to_proto(
                        r,
                        slug_map.get(r.book_id, ""),
                        title_map.get(r.book_id, ""),
                        cover_map.get(r.book_id, "")
                    )
                    for r in rows
                ]
                return app.proto.user_data_pb2.BookshelvesListResponse(
                    bookshelves=protos,
                    total_count=total_count
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserFavourites: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def CreateComment(
        self,
        request: app.proto.user_data_pb2.CreateCommentRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.CommentResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                comment = await app.services.comment_service.create_comment(
                    session, request.user_id, book_id, request.body, request.is_spoiler
                )
                await _book_comments_cache.invalidate_by_book(book_id)
                return app.proto.user_data_pb2.CommentResponse(
                    comment=_comment_to_proto(comment, request.book_slug)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in CreateComment: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpdateComment(
        self,
        request: app.proto.user_data_pb2.UpdateCommentRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.CommentResponse:
        try:
            async with app.database.async_session_maker() as session:
                comment = await app.services.comment_service.update_comment(
                    session, request.comment_id, request.user_id, request.body, request.is_spoiler
                )
                slug_map = await _build_book_slug_map(session, [comment.book_id])
                await _book_comments_cache.invalidate_by_book(comment.book_id)
                return app.proto.user_data_pb2.CommentResponse(
                    comment=_comment_to_proto(comment, slug_map.get(comment.book_id, ""))
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpdateComment: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteComment(
        self,
        request: app.proto.user_data_pb2.DeleteCommentRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id_result = await session.execute(
                    sqlalchemy.text(
                        "SELECT book_id FROM user_data.comments WHERE comment_id = :id"
                    ),
                    {"id": request.comment_id}
                )
                book_id_row = book_id_result.fetchone()
                await app.services.comment_service.delete_comment(
                    session, request.comment_id, request.user_id
                )
                if book_id_row:
                    await _book_comments_cache.invalidate_by_book(book_id_row.book_id)
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteComment: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserComments(
        self,
        request: app.proto.user_data_pb2.GetUserCommentsRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.CommentsListResponse:
        try:
            async with app.database.async_session_maker() as session:
                filter_book_id: typing.Optional[int] = None
                filter_slug: str = ""
                if request.book_slug:
                    filter_book_id, _, _ = await _resolve_book(session, request.book_slug)
                    filter_slug = request.book_slug

                rows, total_count = await app.services.comment_service.get_user_comments(
                    session,
                    request.user_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.sort_by or "created_at",
                    request.order or "desc",
                    filter_book_id
                )

                if filter_slug:
                    slug_map = {r.book_id: filter_slug for r in rows}
                else:
                    slug_map = await _build_book_slug_map(session, [r.book_id for r in rows])

                protos = [_comment_to_proto(r, slug_map.get(r.book_id, "")) for r in rows]
                return app.proto.user_data_pb2.CommentsListResponse(
                    comments=protos,
                    total_count=total_count
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserComments: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetBookComments(
        self,
        request: app.proto.user_data_pb2.GetBookCommentsRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.BookCommentsResponse:
        try:
            limit = request.limit or 10
            offset = request.offset or 0
            sort_by = request.sort_by or "created_at"
            order_dir = "ASC" if (request.order or "desc") == "asc" else "DESC"
            include_spoilers = request.include_spoilers
            sort_col = _VALID_SORT_COLS.get(sort_by, "c.created_at")

            async with app.database.async_session_maker() as session:
                book_result = await session.execute(
                    sqlalchemy.text("SELECT book_id FROM books.books WHERE slug = :slug"),
                    {"slug": request.book_slug}
                )
                book_row = book_result.fetchone()
                if book_row is None:
                    await context.abort(grpc.StatusCode.NOT_FOUND, f"Book not found: {request.book_slug}")
                    return
                book_id = book_row.book_id

                cache_key = f"{book_id}:{sort_by}:{order_dir}:{include_spoilers}:{limit}:{offset}"
                cached = await _book_comments_cache.get(cache_key)

                if cached is None:
                    where = "c.book_id = :book_id AND c.is_deleted = FALSE"
                    params: typing.Dict[str, typing.Any] = {
                        "book_id": book_id, "limit": limit, "offset": offset
                    }
                    if not include_spoilers:
                        where += " AND c.is_spoiler = FALSE"

                    count_result = await session.execute(
                        sqlalchemy.text(
                            f"SELECT COUNT(*) FROM user_data.comments c WHERE {where}"
                        ),
                        params
                    )
                    total_count = count_result.scalar_one()

                    rows_result = await session.execute(
                        sqlalchemy.text(f"""
                            SELECT c.comment_id, c.user_id, c.book_id, c.body, c.is_spoiler,
                                   c.created_at, c.updated_at,
                                   r.overall_rating, r.review_text, r.pacing, r.emotional_impact,
                                   r.intellectual_depth, r.writing_quality, r.rereadability,
                                   r.readability, r.plot_complexity, r.humor
                            FROM user_data.comments c
                            LEFT JOIN user_data.ratings r
                                   ON r.user_id = c.user_id AND r.book_id = c.book_id
                            WHERE {where}
                            ORDER BY {sort_col} {order_dir} NULLS LAST, c.created_at DESC
                            LIMIT :limit OFFSET :offset
                        """),
                        params
                    )
                    rows = rows_result.fetchall()
                    cached = (total_count, rows)
                    await _book_comments_cache.set(cache_key, cached)

                total_count, rows = cached
                comments = [_row_to_comment_with_rating(row, request.book_slug) for row in rows]

                my_entry = None
                if request.requesting_user_id:
                    my_row_result = await session.execute(
                        sqlalchemy.text("""
                            SELECT c.comment_id, c.user_id, c.book_id, c.body, c.is_spoiler,
                                   c.created_at, c.updated_at,
                                   r.overall_rating, r.review_text, r.pacing, r.emotional_impact,
                                   r.intellectual_depth, r.writing_quality, r.rereadability,
                                   r.readability, r.plot_complexity, r.humor
                            FROM user_data.comments c
                            LEFT JOIN user_data.ratings r
                                   ON r.user_id = c.user_id AND r.book_id = c.book_id
                            WHERE c.user_id = :user_id AND c.book_id = :book_id
                              AND c.is_deleted = FALSE
                        """),
                        {"user_id": request.requesting_user_id, "book_id": book_id}
                    )
                    my_row = my_row_result.fetchone()
                    if my_row:
                        my_entry = _row_to_comment_with_rating(my_row, request.book_slug)

                kwargs: typing.Dict[str, typing.Any] = {
                    "comments": comments,
                    "total_count": total_count
                }
                if my_entry is not None:
                    kwargs["my_entry"] = my_entry
                return app.proto.user_data_pb2.BookCommentsResponse(**kwargs)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookComments: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get book comments failed: {e}")


async def _build_book_slug_map(
    session,
    book_ids: typing.List[int]
) -> typing.Dict[int, str]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text("SELECT book_id, slug FROM books.books WHERE book_id = ANY(:ids)"),
        {"ids": unique_ids}
    )
    return {row.book_id: row.slug for row in result.fetchall()}


async def _build_book_title_map(
    session,
    book_ids: typing.List[int]
) -> typing.Dict[int, str]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text("SELECT book_id, title FROM books.books WHERE book_id = ANY(:ids)"),
        {"ids": unique_ids}
    )
    return {row.book_id: (row.title or "") for row in result.fetchall()}


async def _build_book_cover_map(
    session,
    book_ids: typing.List[int]
) -> typing.Dict[int, str]:
    if not book_ids:
        return {}
    unique_ids = list(set(book_ids))
    result = await session.execute(
        sqlalchemy.text("SELECT book_id, primary_cover_url FROM books.books WHERE book_id = ANY(:ids)"),
        {"ids": unique_ids}
    )
    return {row.book_id: (row.primary_cover_url or "") for row in result.fetchall()}
