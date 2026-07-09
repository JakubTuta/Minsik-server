import logging

import app.config
from app.grpc_clients import base
import app.proto.recommendation_pb2
import app.proto.recommendation_pb2_grpc

logger = logging.getLogger(__name__)


class RecommendationClient(base.GrpcClientBase):
    service_label = "recommendation"

    def _target(self) -> str:
        return app.config.settings.recommendation_service_url

    def _create_stub(self, channel):
        return app.proto.recommendation_pb2_grpc.RecommendationServiceStub(channel)


    async def get_recommendation_list(
        self,
        category: str,
        limit: int = 20,
        offset: int = 0,
        language: str = "en",
        user_id: int = 0,
    ) -> app.proto.recommendation_pb2.RecommendationListResponse:
        request = app.proto.recommendation_pb2.GetRecommendationListRequest(
            category=category,
            limit=limit,
            offset=offset,
            language=language,
            user_id=user_id,
        )
        return await self._call("GetRecommendationList", request, timeout=app.config.settings.grpc_recommendation_timeout)

    async def get_home_page(
        self,
        items_per_category: int = 20,
        user_id: int = 0,
        language: str = "en",
    ) -> app.proto.recommendation_pb2.HomePageResponse:
        request = app.proto.recommendation_pb2.GetHomePageRequest(
            items_per_category=items_per_category,
            user_id=user_id,
            language=language,
        )
        return await self._call("GetHomePage", request, timeout=app.config.settings.grpc_recommendation_timeout)

    async def refresh_personal_home(
        self,
        user_id: int,
    ) -> app.proto.recommendation_pb2.HomePageResponse:
        request = app.proto.recommendation_pb2.GetHomePageRequest(
            items_per_category=0,
            user_id=user_id,
        )
        return await self._call("GetHomePage", request, timeout=app.config.settings.grpc_admin_timeout)

    async def get_available_categories(
        self,
    ) -> app.proto.recommendation_pb2.AvailableCategoriesResponse:
        request = app.proto.recommendation_pb2.GetAvailableCategoriesRequest()
        return await self._call("GetAvailableCategories", request, timeout=app.config.settings.grpc_recommendation_timeout)

    async def refresh_recommendations(
        self,
    ) -> app.proto.recommendation_pb2.RefreshRecommendationsResponse:
        request = app.proto.recommendation_pb2.RefreshRecommendationsRequest()
        return await self._call("RefreshRecommendations", request, timeout=app.config.settings.grpc_admin_timeout)

    async def refresh_personal_recommendations(
        self,
    ) -> app.proto.recommendation_pb2.RefreshPersonalRecommendationsResponse:
        request = app.proto.recommendation_pb2.RefreshPersonalRecommendationsRequest()
        return await self._call("RefreshPersonalRecommendations", request, timeout=app.config.settings.grpc_admin_timeout)

    async def refresh_user_personal_recommendations(
        self,
        username: str,
    ) -> app.proto.recommendation_pb2.RefreshUserPersonalRecommendationsResponse:
        request = app.proto.recommendation_pb2.RefreshUserPersonalRecommendationsRequest(
            username=username,
        )
        return await self._call("RefreshUserPersonalRecommendations", request, timeout=app.config.settings.grpc_admin_timeout)

    async def refresh_contextual_recommendations(
        self,
    ) -> app.proto.recommendation_pb2.RefreshContextualRecommendationsResponse:
        request = app.proto.recommendation_pb2.RefreshContextualRecommendationsRequest()
        return await self._call("RefreshContextualRecommendations", request, timeout=app.config.settings.grpc_admin_timeout)

    async def invalidate_contextual_cache(
        self,
        entity_type: str,
        slug: str,
    ) -> app.proto.recommendation_pb2.InvalidateContextualCacheResponse:
        request = app.proto.recommendation_pb2.InvalidateContextualCacheRequest(
            entity_type=entity_type,
            slug=slug,
        )
        return await self._call("InvalidateContextualCache", request, timeout=app.config.settings.grpc_admin_timeout)

    async def invalidate_user_recommendations(
        self,
        user_id: int,
    ) -> app.proto.recommendation_pb2.InvalidateUserRecommendationsResponse:
        request = app.proto.recommendation_pb2.InvalidateUserRecommendationsRequest(
            user_id=user_id,
        )
        return await self._call("InvalidateUserRecommendations", request, timeout=app.config.settings.grpc_timeout)

    async def refresh_book_of_the_week(
        self,
    ) -> app.proto.recommendation_pb2.RefreshBookOfTheWeekResponse:
        request = app.proto.recommendation_pb2.RefreshBookOfTheWeekRequest()
        return await self._call("RefreshBookOfTheWeek", request, timeout=app.config.settings.grpc_admin_timeout)

    async def get_book_recommendations(
        self,
        book_id: int,
        limit_per_section: int = 15,
        user_id: int = 0,
    ) -> app.proto.recommendation_pb2.BookRecommendationsResponse:
        request = app.proto.recommendation_pb2.GetBookRecommendationsRequest(
            book_id=book_id,
            limit_per_section=limit_per_section,
            user_id=user_id,
        )
        return await self._call("GetBookRecommendations", request, timeout=app.config.settings.grpc_recommendation_timeout)

    async def get_author_recommendations(
        self,
        author_id: int,
        limit_per_section: int = 15,
        user_id: int = 0,
    ) -> app.proto.recommendation_pb2.AuthorRecommendationsResponse:
        request = app.proto.recommendation_pb2.GetAuthorRecommendationsRequest(
            author_id=author_id,
            limit_per_section=limit_per_section,
            user_id=user_id,
        )
        return await self._call("GetAuthorRecommendations", request, timeout=app.config.settings.grpc_recommendation_timeout)

    async def get_series_recommendations(
        self,
        series_id: int,
        limit_per_section: int = 15,
    ) -> app.proto.recommendation_pb2.SeriesRecommendationsResponse:
        request = app.proto.recommendation_pb2.GetSeriesRecommendationsRequest(
            series_id=series_id,
            limit_per_section=limit_per_section,
        )
        return await self._call("GetSeriesRecommendations", request, timeout=app.config.settings.grpc_recommendation_timeout)

    async def get_book_of_the_week(
        self,
        language: str = "en",
    ) -> app.proto.recommendation_pb2.BookOfTheWeekResponse:
        request = app.proto.recommendation_pb2.GetBookOfTheWeekRequest(language=language)
        return await self._call("GetBookOfTheWeek", request, timeout=app.config.settings.grpc_recommendation_timeout)


recommendation_client = RecommendationClient()
