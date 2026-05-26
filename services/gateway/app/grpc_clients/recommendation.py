import logging
import typing

import app.config
import app.proto.recommendation_pb2 as recommendation_pb2
import app.proto.recommendation_pb2_grpc as recommendation_pb2_grpc
import app.tracing
import grpc

logger = logging.getLogger(__name__)


class RecommendationClient:
    def __init__(self):
        self.channel: typing.Optional[grpc.aio.Channel] = None
        self.stub: typing.Optional[
            recommendation_pb2_grpc.RecommendationServiceStub
        ] = None

    async def connect(self):
        self.channel = grpc.aio.insecure_channel(
            app.config.settings.recommendation_service_url,
            options=[
                ("grpc.keepalive_time_ms", app.config.settings.grpc_keepalive_time_ms),
                (
                    "grpc.keepalive_timeout_ms",
                    app.config.settings.grpc_keepalive_timeout_ms,
                ),
                ("grpc.keepalive_permit_without_calls", 0),
                ("grpc.http2.max_pings_without_data", 0),
            ],
            interceptors=app.tracing.get_client_interceptors(),
        )
        self.stub = recommendation_pb2_grpc.RecommendationServiceStub(self.channel)
        logger.info(
            f"Connected to recommendation service at {app.config.settings.recommendation_service_url}"
        )

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("Closed recommendation service connection")

    async def get_recommendation_list(
        self,
        category: str,
        limit: int = 20,
        offset: int = 0,
        language: str = "en",
    ) -> recommendation_pb2.RecommendationListResponse:
        request = recommendation_pb2.GetRecommendationListRequest(
            category=category,
            limit=limit,
            offset=offset,
            language=language,
        )
        try:
            return await self.stub.GetRecommendationList(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in get_recommendation_list: {e.code()} - {e.details()}"
            )
            raise

    async def get_home_page(
        self,
        items_per_category: int = 20,
        user_id: int = 0,
        language: str = "en",
    ) -> recommendation_pb2.HomePageResponse:
        request = recommendation_pb2.GetHomePageRequest(
            items_per_category=items_per_category,
            user_id=user_id,
            language=language,
        )
        try:
            return await self.stub.GetHomePage(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(f"gRPC error in get_home_page: {e.code()} - {e.details()}")
            raise

    async def refresh_personal_home(
        self,
        user_id: int,
    ) -> recommendation_pb2.HomePageResponse:
        request = recommendation_pb2.GetHomePageRequest(
            items_per_category=0,
            user_id=user_id,
        )
        try:
            return await self.stub.GetHomePage(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in refresh_personal_home: {e.code()} - {e.details()}"
            )
            raise

    async def get_available_categories(
        self,
    ) -> recommendation_pb2.AvailableCategoriesResponse:
        request = recommendation_pb2.GetAvailableCategoriesRequest()
        try:
            return await self.stub.GetAvailableCategories(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in get_available_categories: {e.code()} - {e.details()}"
            )
            raise

    async def refresh_recommendations(
        self,
    ) -> recommendation_pb2.RefreshRecommendationsResponse:
        request = recommendation_pb2.RefreshRecommendationsRequest()
        try:
            return await self.stub.RefreshRecommendations(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in refresh_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def refresh_personal_recommendations(
        self,
    ) -> recommendation_pb2.RefreshPersonalRecommendationsResponse:
        request = recommendation_pb2.RefreshPersonalRecommendationsRequest()
        try:
            return await self.stub.RefreshPersonalRecommendations(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in refresh_personal_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def refresh_user_personal_recommendations(
        self,
        username: str,
    ) -> recommendation_pb2.RefreshUserPersonalRecommendationsResponse:
        request = recommendation_pb2.RefreshUserPersonalRecommendationsRequest(
            username=username,
        )
        try:
            return await self.stub.RefreshUserPersonalRecommendations(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in refresh_user_personal_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def refresh_contextual_recommendations(
        self,
    ) -> recommendation_pb2.RefreshContextualRecommendationsResponse:
        request = recommendation_pb2.RefreshContextualRecommendationsRequest()
        try:
            return await self.stub.RefreshContextualRecommendations(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in refresh_contextual_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def invalidate_contextual_cache(
        self,
        entity_type: str,
        slug: str,
    ) -> recommendation_pb2.InvalidateContextualCacheResponse:
        request = recommendation_pb2.InvalidateContextualCacheRequest(
            entity_type=entity_type,
            slug=slug,
        )
        try:
            return await self.stub.InvalidateContextualCache(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in invalidate_contextual_cache: {e.code()} - {e.details()}"
            )
            raise

    async def refresh_book_of_the_week(
        self,
    ) -> recommendation_pb2.RefreshBookOfTheWeekResponse:
        request = recommendation_pb2.RefreshBookOfTheWeekRequest()
        try:
            return await self.stub.RefreshBookOfTheWeek(
                request,
                timeout=app.config.settings.grpc_admin_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in refresh_book_of_the_week: {e.code()} - {e.details()}"
            )
            raise

    async def get_book_recommendations(
        self,
        book_id: int,
        limit_per_section: int = 15,
        user_id: int = 0,
    ) -> recommendation_pb2.BookRecommendationsResponse:
        request = recommendation_pb2.GetBookRecommendationsRequest(
            book_id=book_id,
            limit_per_section=limit_per_section,
            user_id=user_id,
        )
        try:
            return await self.stub.GetBookRecommendations(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in get_book_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def get_author_recommendations(
        self,
        author_id: int,
        limit_per_section: int = 15,
        user_id: int = 0,
    ) -> recommendation_pb2.AuthorRecommendationsResponse:
        request = recommendation_pb2.GetAuthorRecommendationsRequest(
            author_id=author_id,
            limit_per_section=limit_per_section,
            user_id=user_id,
        )
        try:
            return await self.stub.GetAuthorRecommendations(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in get_author_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def get_series_recommendations(
        self,
        series_id: int,
        limit_per_section: int = 15,
    ) -> recommendation_pb2.SeriesRecommendationsResponse:
        request = recommendation_pb2.GetSeriesRecommendationsRequest(
            series_id=series_id,
            limit_per_section=limit_per_section,
        )
        try:
            return await self.stub.GetSeriesRecommendations(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in get_series_recommendations: {e.code()} - {e.details()}"
            )
            raise

    async def get_book_of_the_week(
        self,
        language: str = "en",
    ) -> recommendation_pb2.BookOfTheWeekResponse:
        request = recommendation_pb2.GetBookOfTheWeekRequest(language=language)
        try:
            return await self.stub.GetBookOfTheWeek(
                request,
                timeout=app.config.settings.grpc_recommendation_timeout,
            )
        except grpc.RpcError as e:
            logger.error(
                f"gRPC error in get_book_of_the_week: {e.code()} - {e.details()}"
            )
            raise


recommendation_client = RecommendationClient()
