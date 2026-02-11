import typing
import logging
import grpc
import sqlalchemy
import app.database
import app.proto.user_data_pb2
import app.proto.user_data_pb2_grpc
import app.services.bookshelf_service
import app.services.rating_service
import app.services.comment_service
import app.services.note_service

logger = logging.getLogger(__name__)

_NOT_FOUND_ERRORS = {"not_found", "book_not_found", "user_not_found"}
_PERMISSION_ERRORS = {"not_owner"}


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


def _note_to_proto(
    note,
    book_slug: str = ""
) -> app.proto.user_data_pb2.Note:
    return app.proto.user_data_pb2.Note(
        note_id=note.note_id,
        user_id=note.user_id,
        book_id=note.book_id,
        book_slug=book_slug,
        note_text=note.note_text,
        page_number=note.page_number or 0,
        has_page_number=note.page_number is not None,
        is_spoiler=note.is_spoiler,
        created_at=note.created_at.isoformat() if note.created_at else "",
        updated_at=note.updated_at.isoformat() if note.updated_at else ""
    )


async def _handle_error(error: Exception, context: grpc.aio.ServicerContext) -> None:
    error_key = str(error)
    if error_key in _NOT_FOUND_ERRORS:
        await context.abort(grpc.StatusCode.NOT_FOUND, f"Resource not found: {error_key}")
    elif error_key in _PERMISSION_ERRORS:
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, f"Permission denied: {error_key}")
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

    async def GetBookComments(
        self,
        request: app.proto.user_data_pb2.GetBookCommentsRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.CommentsListResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                rows, total_count = await app.services.comment_service.get_book_comments(
                    session,
                    book_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.order or "desc",
                    request.include_spoilers
                )
                protos = [_comment_to_proto(r, request.book_slug) for r in rows]
                return app.proto.user_data_pb2.CommentsListResponse(
                    comments=protos,
                    total_count=total_count
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookComments: {e}")
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
                await app.services.comment_service.delete_comment(
                    session, request.comment_id, request.user_id
                )
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

    async def GetBookNotes(
        self,
        request: app.proto.user_data_pb2.GetBookNotesRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.NotesListResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                rows, total_count = await app.services.note_service.get_book_notes(
                    session,
                    request.user_id,
                    book_id,
                    request.limit or 10,
                    request.offset or 0,
                    request.sort_by or "page_number",
                    request.order or "asc"
                )
                protos = [_note_to_proto(r, request.book_slug) for r in rows]
                return app.proto.user_data_pb2.NotesListResponse(
                    notes=protos,
                    total_count=total_count
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookNotes: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def CreateNote(
        self,
        request: app.proto.user_data_pb2.CreateNoteRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.NoteResponse:
        try:
            async with app.database.async_session_maker() as session:
                book_id, _, _ = await _resolve_book(session, request.book_slug)
                page_number = request.page_number if request.has_page_number else None
                note = await app.services.note_service.create_note(
                    session, request.user_id, book_id, request.note_text, page_number, request.is_spoiler
                )
                return app.proto.user_data_pb2.NoteResponse(
                    note=_note_to_proto(note, request.book_slug)
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in CreateNote: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def UpdateNote(
        self,
        request: app.proto.user_data_pb2.UpdateNoteRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.NoteResponse:
        try:
            async with app.database.async_session_maker() as session:
                page_number = request.page_number if request.has_page_number else None
                note = await app.services.note_service.update_note(
                    session, request.note_id, request.user_id, request.note_text, page_number, request.is_spoiler
                )
                slug_map = await _build_book_slug_map(session, [note.book_id])
                return app.proto.user_data_pb2.NoteResponse(
                    note=_note_to_proto(note, slug_map.get(note.book_id, ""))
                )
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpdateNote: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def DeleteNote(
        self,
        request: app.proto.user_data_pb2.DeleteNoteRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                await app.services.note_service.delete_note(
                    session, request.note_id, request.user_id
                )
                return app.proto.user_data_pb2.EmptyResponse()
        except ValueError as e:
            await _handle_error(e, context)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteNote: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")

    async def GetUserNotes(
        self,
        request: app.proto.user_data_pb2.GetUserNotesRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.user_data_pb2.NotesListResponse:
        try:
            async with app.database.async_session_maker() as session:
                rows, total_count = await app.services.note_service.get_user_notes(
                    session,
                    request.user_id,
                    request.limit or 10,
                    request.offset or 0
                )

                slug_map = await _build_book_slug_map(session, [r.book_id for r in rows])
                protos = [_note_to_proto(r, slug_map.get(r.book_id, "")) for r in rows]
                return app.proto.user_data_pb2.NotesListResponse(
                    notes=protos,
                    total_count=total_count
                )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetUserNotes: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {e}")


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
