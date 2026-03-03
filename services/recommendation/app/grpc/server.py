import logging

import app.db
import app.proto.recommendation_pb2 as recommendation_pb2
import app.proto.recommendation_pb2_grpc as recommendation_pb2_grpc
import app.services.contextual_provider
import app.services.list_builder
import app.services.list_provider
import grpc

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


def _dict_to_section(section: dict) -> recommendation_pb2.RecommendationSection:
    item_type = section.get("item_type", "book")
    proto_section = recommendation_pb2.RecommendationSection(
        section_key=section["section_key"],
        display_name=section["display_name"],
        item_type=item_type,
        total=section["total"],
    )
    if item_type == "book":
        for item in section.get("book_items", []):
            proto_section.book_items.append(_dict_to_book_item(item))
    else:
        for item in section.get("author_items", []):
            proto_section.author_items.append(_dict_to_author_item(item))
    return proto_section


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
                await context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Unknown category: {request.category}"
                )
                return

            limit = request.limit if request.limit > 0 else 20
            offset = request.offset if request.offset >= 0 else 0

            data = await app.services.list_provider.get_list(
                request.category, limit, offset
            )
            if data is None:
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE, "Recommendations not yet generated"
                )
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
            items_per_category = (
                request.items_per_category if request.items_per_category > 0 else 20
            )
            user_id = request.user_id if request.user_id > 0 else 0
            categories = await app.services.list_provider.get_home_page(
                items_per_category, user_id
            )
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
            await app.services.list_builder.refresh_all(app.db.async_session_maker)
            return recommendation_pb2.RefreshRecommendationsResponse(
                success=True,
                message="Recommendation lists refreshed successfully",
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")

    async def GetBookRecommendations(
        self,
        request: recommendation_pb2.GetBookRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.BookRecommendationsResponse:
        try:
            limit = request.limit_per_section if request.limit_per_section > 0 else 15
            user_id = request.user_id if request.user_id > 0 else 0
            sections = await app.services.contextual_provider.get_book_recommendations(
                request.book_id, limit, user_id
            )
            if sections is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Book with ID {request.book_id} not found",
                )
                return
            response = recommendation_pb2.BookRecommendationsResponse(book_id=request.book_id)
            for section in sections:
                response.sections.append(_dict_to_section(section))
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    async def GetAuthorRecommendations(
        self,
        request: recommendation_pb2.GetAuthorRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> recommendation_pb2.AuthorRecommendationsResponse:
        try:
            limit = request.limit_per_section if request.limit_per_section > 0 else 15
            user_id = request.user_id if request.user_id > 0 else 0
            sections = await app.services.contextual_provider.get_author_recommendations(
                request.author_id, limit, user_id
            )
            if sections is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Author with ID {request.author_id} not found",
                )
                return
            response = recommendation_pb2.AuthorRecommendationsResponse(author_id=request.author_id)
            for section in sections:
                response.sections.append(_dict_to_section(section))
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetAuthorRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")
