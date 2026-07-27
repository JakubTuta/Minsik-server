import logging
import typing

import app.config
from app.grpc_clients import base
import app.proto.user_data_pb2
import app.proto.user_data_pb2_grpc

logger = logging.getLogger(__name__)


class UserDataClient(base.GrpcClientBase):
    service_label = "user_data"

    def _target(self) -> str:
        return app.config.settings.user_data_service_url

    def _create_stub(self, channel):
        return app.proto.user_data_pb2_grpc.UserDataServiceStub(channel)


    async def get_bookshelf(
        self, user_id: int, book_slug: str, language: str = "en"
    ) -> app.proto.user_data_pb2.BookshelfResponse:
        request = app.proto.user_data_pb2.GetBookshelfRequest(
            user_id=user_id, book_slug=book_slug, language=language
        )
        return await self._call("GetBookshelf", request)

    async def get_user_book_info(
        self, user_id: int, book_slug: str, language: str = "en"
    ) -> app.proto.user_data_pb2.UserBookInfoResponse:
        request = app.proto.user_data_pb2.GetUserBookInfoRequest(
            user_id=user_id, book_slug=book_slug, language=language
        )
        return await self._call("GetUserBookInfo", request)

    async def get_book_statuses(
        self, user_id: int, book_ids: typing.List[int]
    ) -> app.proto.user_data_pb2.BookStatusesResponse:
        request = app.proto.user_data_pb2.GetBookStatusesRequest(
            user_id=user_id, book_ids=book_ids
        )
        return await self._call("GetBookStatuses", request)

    async def upsert_bookshelf(
        self, user_id: int, book_slug: str, status: str, language: str = "en"
    ) -> app.proto.user_data_pb2.BookshelfResponse:
        request = app.proto.user_data_pb2.UpsertBookshelfRequest(
            user_id=user_id, book_slug=book_slug, status=status, language=language
        )
        return await self._call("UpsertBookshelf", request)

    async def delete_bookshelf(
        self, user_id: int, book_slug: str, language: str = "en"
    ) -> app.proto.user_data_pb2.EmptyResponse:
        request = app.proto.user_data_pb2.DeleteBookshelfRequest(
            user_id=user_id, book_slug=book_slug, language=language
        )
        return await self._call("DeleteBookshelf", request)

    async def get_user_bookshelves(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        status_filter: str = "",
        favourites_only: bool = False,
        sort_by: str = "created_at",
        order: str = "desc",
        language: str = "en",
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        request = app.proto.user_data_pb2.GetUserBookshelvesRequest(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            favourites_only=favourites_only,
            sort_by=sort_by,
            order=order,
            language=language,
        )
        return await self._call("GetUserBookshelves", request)

    async def get_public_bookshelves(
        self,
        username: str,
        limit: int = 10,
        offset: int = 0,
        status_filter: str = "",
        favourites_only: bool = False,
        sort_by: str = "created_at",
        order: str = "desc",
        language: str = "en",
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        request = app.proto.user_data_pb2.GetPublicBookshelvesRequest(
            username=username,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            favourites_only=favourites_only,
            sort_by=sort_by,
            order=order,
            language=language,
        )
        return await self._call("GetPublicBookshelves", request)

    async def get_rating(
        self, user_id: int, book_slug: str, language: str = "en"
    ) -> app.proto.user_data_pb2.RatingResponse:
        request = app.proto.user_data_pb2.GetRatingRequest(
            user_id=user_id, book_slug=book_slug, language=language
        )
        return await self._call("GetRating", request)

    async def upsert_rating(
        self,
        user_id: int,
        book_slug: str,
        overall_rating: float,
        review_text: str = "",
        pacing: typing.Optional[float] = None,
        emotional_impact: typing.Optional[float] = None,
        intellectual_depth: typing.Optional[float] = None,
        writing_quality: typing.Optional[float] = None,
        rereadability: typing.Optional[float] = None,
        readability: typing.Optional[float] = None,
        plot_complexity: typing.Optional[float] = None,
        humor: typing.Optional[float] = None,
        language: str = "en",
    ) -> app.proto.user_data_pb2.RatingResponse:
        request = app.proto.user_data_pb2.UpsertRatingRequest(
            user_id=user_id,
            book_slug=book_slug,
            overall_rating=overall_rating,
            review_text=review_text or "",
            pacing=pacing or 0.0,
            has_pacing=pacing is not None,
            emotional_impact=emotional_impact or 0.0,
            has_emotional_impact=emotional_impact is not None,
            intellectual_depth=intellectual_depth or 0.0,
            has_intellectual_depth=intellectual_depth is not None,
            writing_quality=writing_quality or 0.0,
            has_writing_quality=writing_quality is not None,
            rereadability=rereadability or 0.0,
            has_rereadability=rereadability is not None,
            readability=readability or 0.0,
            has_readability=readability is not None,
            plot_complexity=plot_complexity or 0.0,
            has_plot_complexity=plot_complexity is not None,
            humor=humor or 0.0,
            has_humor=humor is not None,
            language=language,
        )
        return await self._call("UpsertRating", request)

    async def delete_rating(
        self, user_id: int, book_slug: str, language: str = "en"
    ) -> app.proto.user_data_pb2.EmptyResponse:
        request = app.proto.user_data_pb2.DeleteRatingRequest(
            user_id=user_id, book_slug=book_slug, language=language
        )
        return await self._call("DeleteRating", request)

    async def get_user_ratings(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        min_rating: float = 0.0,
        max_rating: float = 0.0,
        language: str = "en",
    ) -> app.proto.user_data_pb2.RatingsListResponse:
        request = app.proto.user_data_pb2.GetUserRatingsRequest(
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            min_rating=min_rating,
            max_rating=max_rating,
            language=language,
        )
        return await self._call("GetUserRatings", request)

    async def toggle_favourite(
        self, user_id: int, book_slug: str, is_favorite: bool, language: str = "en"
    ) -> app.proto.user_data_pb2.FavouriteResponse:
        request = app.proto.user_data_pb2.ToggleFavouriteRequest(
            user_id=user_id,
            book_slug=book_slug,
            is_favorite=is_favorite,
            language=language,
        )
        return await self._call("ToggleFavourite", request)

    async def get_user_favourites(
        self, user_id: int, limit: int = 10, offset: int = 0, language: str = "en"
    ) -> app.proto.user_data_pb2.BookshelvesListResponse:
        request = app.proto.user_data_pb2.GetUserFavouritesRequest(
            user_id=user_id, limit=limit, offset=offset, language=language
        )
        return await self._call("GetUserFavourites", request)

    async def create_comment(
        self,
        user_id: int,
        book_slug: str,
        body: str,
        is_spoiler: bool,
        language: str = "en",
    ) -> app.proto.user_data_pb2.CommentResponse:
        request = app.proto.user_data_pb2.CreateCommentRequest(
            user_id=user_id,
            book_slug=book_slug,
            body=body,
            is_spoiler=is_spoiler,
            language=language,
        )
        return await self._call("CreateComment", request)

    async def update_comment(
        self, comment_id: int, user_id: int, body: str, is_spoiler: bool
    ) -> app.proto.user_data_pb2.CommentResponse:
        request = app.proto.user_data_pb2.UpdateCommentRequest(
            comment_id=comment_id, user_id=user_id, body=body, is_spoiler=is_spoiler
        )
        return await self._call("UpdateComment", request)

    async def delete_comment(
        self, comment_id: int, user_id: int
    ) -> app.proto.user_data_pb2.EmptyResponse:
        request = app.proto.user_data_pb2.DeleteCommentRequest(
            comment_id=comment_id, user_id=user_id
        )
        return await self._call("DeleteComment", request)

    async def get_user_comments(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        book_slug: str = "",
        language: str = "en",
    ) -> app.proto.user_data_pb2.CommentsListResponse:
        request = app.proto.user_data_pb2.GetUserCommentsRequest(
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            book_slug=book_slug,
            language=language,
        )
        return await self._call("GetUserComments", request)

    async def get_book_comments(
        self,
        book_slug: str,
        limit: int = 10,
        offset: int = 0,
        order: str = "desc",
        include_spoilers: bool = False,
        sort_by: str = "created_at",
        requesting_user_id: int = 0,
        rating_filters: typing.List[float] = [],
        language: str = "en",
    ) -> app.proto.user_data_pb2.BookCommentsResponse:
        request = app.proto.user_data_pb2.GetBookCommentsRequest(
            book_slug=book_slug,
            limit=limit,
            offset=offset,
            order=order,
            include_spoilers=include_spoilers,
            sort_by=sort_by,
            requesting_user_id=requesting_user_id,
            rating_filters=rating_filters,
            language=language,
        )
        return await self._call("GetBookComments", request)

    async def get_public_profile_stats(
        self, username: str
    ) -> app.proto.user_data_pb2.ProfileStatsResponse:
        request = app.proto.user_data_pb2.GetPublicProfileStatsRequest(username=username)
        return await self._call("GetPublicProfileStats", request)

    async def get_profile_overview(
        self, username: str, language: str = "en"
    ) -> app.proto.user_data_pb2.ProfileOverviewResponse:
        request = app.proto.user_data_pb2.GetProfileOverviewRequest(
            username=username, language=language
        )
        return await self._call("GetProfileOverview", request)

    async def get_year_in_review(
        self, user_id: int, year: int = 0, language: str = "en"
    ) -> app.proto.user_data_pb2.YearInReviewResponse:
        request = app.proto.user_data_pb2.GetYearInReviewRequest(
            user_id=user_id, year=year, language=language
        )
        return await self._call("GetYearInReview", request)

    async def delete_user_data(self, user_id: int) -> app.proto.user_data_pb2.EmptyResponse:
        request = app.proto.user_data_pb2.DeleteUserDataRequest(user_id=user_id)
        return await self._call("DeleteUserData", request)


user_data_client = UserDataClient()
