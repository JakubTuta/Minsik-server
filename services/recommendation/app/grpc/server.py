import logging

import grpc

import app.db
import app.proto.recommendation_pb2 as recommendation_pb2
import app.proto.recommendation_pb2_grpc as recommendation_pb2_grpc
import app.services.list_builder
import app.services.list_provider

logger = logging.getLogger(__name__)


def _dict_to_book_item(item: dict) -> recommendation_pb2.RecommendationBookItem:
    return recommendation_pb2.RecommendationBookItem(
        book_id=item["book_id"],
        title=item["title"],
        slug=item["slug"],
        language=item["language"],
        primary_cover_url=item["primary_cover_url"],
        author_names=item["author_names"],
        author_slugs=item["author_slugs"],
        avg_rating=item["avg_rating"],
        rating_count=item["rating_count"],
        score=item["score"],
    )


def _dict_to_author_item(item: dict) -> recommendation_pb2.RecommendationAuthorItem:
    return recommendation_pb2.RecommendationAuthorItem(
        author_id=item["author_id"],
        name=item["name"],
        slug=item["slug"],
        photo_url=item["photo_url"],
        book_count=item["book_count"],
        score=item["score"],
    )


def _dict_to_list_response(data: dict) -> recommendation_pb2.RecommendationListResponse:
    item_type = data.get("item_type", "book")
    response = recommendation_pb2.RecommendationListResponse(
        category=data["category"],
        display_name=data["display_name"],
        item_type=item_type,
        total=data["total"],
    )

    if item_type == "book":
        for item in data.get("book_items", []):
            response.book_items.append(_dict_to_book_item(item))
    else:
        for item in data.get("author_items", []):
            response.author_items.append(_dict_to_author_item(item))

    return response


class RecommendationServicer(recommendation_pb2_grpc.RecommendationServiceServicer):
    async def GetRecommendationList(
        self,
        request: recommendation_pb2.GetRecommendationListRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.RecommendationListResponse:
        try:
            if request.category not in app.services.list_builder.CATEGORY_KEYS:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Unknown category: {request.category}")
                return

            limit = request.limit if request.limit > 0 else 20
            offset = request.offset if request.offset >= 0 else 0

            data = await app.services.list_provider.get_list(request.category, limit, offset)
            if data is None:
                await context.abort(grpc.StatusCode.UNAVAILABLE, "Recommendations not yet generated")
                return

            return _dict_to_list_response(data)
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetRecommendationList: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    async def GetHomePage(
        self,
        request: recommendation_pb2.GetHomePageRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.HomePageResponse:
        try:
            items_per_category = request.items_per_category if request.items_per_category > 0 else 20
            categories = await app.services.list_provider.get_home_page(items_per_category)
            response = recommendation_pb2.HomePageResponse()
            for data in categories:
                response.categories.append(_dict_to_list_response(data))
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetHomePage: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    async def GetAvailableCategories(
        self,
        request: recommendation_pb2.GetAvailableCategoriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.AvailableCategoriesResponse:
        try:
            categories = app.services.list_provider.get_available_categories()
            response = recommendation_pb2.AvailableCategoriesResponse()
            for cat in categories:
                response.categories.append(
                    recommendation_pb2.CategoryInfo(
                        category=cat["category"],
                        display_name=cat["display_name"],
                        item_type=cat["item_type"],
                    )
                )
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetAvailableCategories: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    async def RefreshRecommendations(
        self,
        request: recommendation_pb2.RefreshRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.RefreshRecommendationsResponse:
        try:
            async with app.db.async_session_maker() as session:
                await app.services.list_builder.refresh_all(session)
            return recommendation_pb2.RefreshRecommendationsResponse(
                success=True,
                message="Recommendation lists refreshed successfully",
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")
