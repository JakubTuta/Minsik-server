import typing
import grpc
import logging
import app.config
import app.proto.user_data_pb2 as user_data_pb2
import app.proto.user_data_pb2_grpc as user_data_pb2_grpc

logger = logging.getLogger(__name__)


class UserDataClient:
    def __init__(self):
        self.channel: typing.Optional[grpc.aio.Channel] = None
        self.stub: typing.Optional[user_data_pb2_grpc.UserDataServiceStub] = None

    async def connect(self) -> None:
        self.channel = grpc.aio.insecure_channel(
            app.config.settings.user_data_service_url,
            options=[
                ("grpc.keepalive_time_ms", app.config.settings.grpc_keepalive_time_ms),
                ("grpc.keepalive_timeout_ms", app.config.settings.grpc_keepalive_timeout_ms),
                ("grpc.keepalive_permit_without_calls", 1),
                ("grpc.http2.max_pings_without_data", 0),
            ]
        )
        self.stub = user_data_pb2_grpc.UserDataServiceStub(self.channel)
        logger.info(f"Connected to user data service at {app.config.settings.user_data_service_url}")

    async def close(self) -> None:
        if self.channel:
            await self.channel.close()
            logger.info("Closed user data service connection")

    async def get_bookshelf(
        self, user_id: int, book_slug: str
    ) -> user_data_pb2.BookshelfResponse:
        request = user_data_pb2.GetBookshelfRequest(user_id=user_id, book_slug=book_slug)
        try:
            return await self.stub.GetBookshelf(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_bookshelf: {e.code()} - {e.details()}")
            raise

    async def get_user_book_info(
        self, user_id: int, book_slug: str
    ) -> user_data_pb2.UserBookInfoResponse:
        request = user_data_pb2.GetUserBookInfoRequest(user_id=user_id, book_slug=book_slug)
        try:
            return await self.stub.GetUserBookInfo(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_user_book_info: {e.code()} - {e.details()}")
            raise

    async def upsert_bookshelf(
        self, user_id: int, book_slug: str, status: str
    ) -> user_data_pb2.BookshelfResponse:
        request = user_data_pb2.UpsertBookshelfRequest(
            user_id=user_id, book_slug=book_slug, status=status
        )
        try:
            return await self.stub.UpsertBookshelf(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in upsert_bookshelf: {e.code()} - {e.details()}")
            raise

    async def delete_bookshelf(
        self, user_id: int, book_slug: str
    ) -> user_data_pb2.EmptyResponse:
        request = user_data_pb2.DeleteBookshelfRequest(user_id=user_id, book_slug=book_slug)
        try:
            return await self.stub.DeleteBookshelf(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in delete_bookshelf: {e.code()} - {e.details()}")
            raise

    async def get_user_bookshelves(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        status_filter: str = "",
        favourites_only: bool = False,
        sort_by: str = "created_at",
        order: str = "desc"
    ) -> user_data_pb2.BookshelvesListResponse:
        request = user_data_pb2.GetUserBookshelvesRequest(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            favourites_only=favourites_only,
            sort_by=sort_by,
            order=order
        )
        try:
            return await self.stub.GetUserBookshelves(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_user_bookshelves: {e.code()} - {e.details()}")
            raise

    async def get_public_bookshelves(
        self,
        username: str,
        limit: int = 10,
        offset: int = 0,
        status_filter: str = "",
        favourites_only: bool = False,
        sort_by: str = "created_at",
        order: str = "desc"
    ) -> user_data_pb2.BookshelvesListResponse:
        request = user_data_pb2.GetPublicBookshelvesRequest(
            username=username,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            favourites_only=favourites_only,
            sort_by=sort_by,
            order=order
        )
        try:
            return await self.stub.GetPublicBookshelves(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_public_bookshelves: {e.code()} - {e.details()}")
            raise

    async def get_rating(
        self, user_id: int, book_slug: str
    ) -> user_data_pb2.RatingResponse:
        request = user_data_pb2.GetRatingRequest(user_id=user_id, book_slug=book_slug)
        try:
            return await self.stub.GetRating(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_rating: {e.code()} - {e.details()}")
            raise

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
        humor: typing.Optional[float] = None
    ) -> user_data_pb2.RatingResponse:
        request = user_data_pb2.UpsertRatingRequest(
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
            has_humor=humor is not None
        )
        try:
            return await self.stub.UpsertRating(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in upsert_rating: {e.code()} - {e.details()}")
            raise

    async def delete_rating(
        self, user_id: int, book_slug: str
    ) -> user_data_pb2.EmptyResponse:
        request = user_data_pb2.DeleteRatingRequest(user_id=user_id, book_slug=book_slug)
        try:
            return await self.stub.DeleteRating(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in delete_rating: {e.code()} - {e.details()}")
            raise

    async def get_user_ratings(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        min_rating: float = 0.0,
        max_rating: float = 0.0
    ) -> user_data_pb2.RatingsListResponse:
        request = user_data_pb2.GetUserRatingsRequest(
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            min_rating=min_rating,
            max_rating=max_rating
        )
        try:
            return await self.stub.GetUserRatings(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_user_ratings: {e.code()} - {e.details()}")
            raise

    async def toggle_favourite(
        self, user_id: int, book_slug: str, is_favorite: bool
    ) -> user_data_pb2.FavouriteResponse:
        request = user_data_pb2.ToggleFavouriteRequest(
            user_id=user_id, book_slug=book_slug, is_favorite=is_favorite
        )
        try:
            return await self.stub.ToggleFavourite(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in toggle_favourite: {e.code()} - {e.details()}")
            raise

    async def get_user_favourites(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> user_data_pb2.BookshelvesListResponse:
        request = user_data_pb2.GetUserFavouritesRequest(
            user_id=user_id, limit=limit, offset=offset
        )
        try:
            return await self.stub.GetUserFavourites(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_user_favourites: {e.code()} - {e.details()}")
            raise

    async def create_comment(
        self, user_id: int, book_slug: str, body: str, is_spoiler: bool
    ) -> user_data_pb2.CommentResponse:
        request = user_data_pb2.CreateCommentRequest(
            user_id=user_id, book_slug=book_slug, body=body, is_spoiler=is_spoiler
        )
        try:
            return await self.stub.CreateComment(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in create_comment: {e.code()} - {e.details()}")
            raise

    async def update_comment(
        self, comment_id: int, user_id: int, body: str, is_spoiler: bool
    ) -> user_data_pb2.CommentResponse:
        request = user_data_pb2.UpdateCommentRequest(
            comment_id=comment_id, user_id=user_id, body=body, is_spoiler=is_spoiler
        )
        try:
            return await self.stub.UpdateComment(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in update_comment: {e.code()} - {e.details()}")
            raise

    async def delete_comment(
        self, comment_id: int, user_id: int
    ) -> user_data_pb2.EmptyResponse:
        request = user_data_pb2.DeleteCommentRequest(comment_id=comment_id, user_id=user_id)
        try:
            return await self.stub.DeleteComment(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in delete_comment: {e.code()} - {e.details()}")
            raise

    async def get_user_comments(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "created_at",
        order: str = "desc",
        book_slug: str = ""
    ) -> user_data_pb2.CommentsListResponse:
        request = user_data_pb2.GetUserCommentsRequest(
            user_id=user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            order=order,
            book_slug=book_slug
        )
        try:
            return await self.stub.GetUserComments(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_user_comments: {e.code()} - {e.details()}")
            raise

    async def get_book_comments(
        self,
        book_slug: str,
        limit: int = 10,
        offset: int = 0,
        order: str = "desc",
        include_spoilers: bool = False,
        sort_by: str = "created_at",
        requesting_user_id: int = 0
    ) -> user_data_pb2.BookCommentsResponse:
        request = user_data_pb2.GetBookCommentsRequest(
            book_slug=book_slug,
            limit=limit,
            offset=offset,
            order=order,
            include_spoilers=include_spoilers,
            sort_by=sort_by,
            requesting_user_id=requesting_user_id
        )
        try:
            return await self.stub.GetBookComments(request, timeout=app.config.settings.grpc_timeout)
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_book_comments: {e.code()} - {e.details()}")
            raise


user_data_client = UserDataClient()
