import logging

import app.cache
import app.db
import app.proto.recommendation_pb2
import app.proto.recommendation_pb2_grpc
import app.services.book_of_week_builder
import app.services.contextual_precompute
import app.services.contextual_provider
import app.services.list_builder
import app.services.list_provider
import app.services.personal_refresher
import grpc
import sqlalchemy

logger = logging.getLogger(__name__)


def _dict_to_book_item(item: dict) -> app.proto.recommendation_pb2.RecommendationBookItem:
    return app.proto.recommendation_pb2.RecommendationBookItem(
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
        readers=item.get("readers", 0),
    )


def _dict_to_author_item(item: dict) -> app.proto.recommendation_pb2.RecommendationAuthorItem:
    return app.proto.recommendation_pb2.RecommendationAuthorItem(
        author_id=item["author_id"],
        name=item["name"],
        slug=item["slug"],
        photo_url=item["photo_url"],
        book_count=item["book_count"],
        score=item["score"],
        avg_rating=item.get("avg_rating", ""),
        rating_count=item.get("rating_count", 0),
        readers=item.get("readers", 0),
    )


def _dict_to_section(section: dict) -> app.proto.recommendation_pb2.RecommendationSection:
    item_type = section.get("item_type", "book")
    proto_section = app.proto.recommendation_pb2.RecommendationSection(
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


def _dict_to_list_response(data: dict) -> app.proto.recommendation_pb2.RecommendationListResponse:
    item_type = data.get("item_type", "book")
    response = app.proto.recommendation_pb2.RecommendationListResponse(
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


class RecommendationServicer(app.proto.recommendation_pb2_grpc.RecommendationServiceServicer):
    async def GetRecommendationList(
        self,
        request: app.proto.recommendation_pb2.GetRecommendationListRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.RecommendationListResponse:
        try:
            if request.category not in app.services.list_builder.CATEGORY_KEYS:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND, f"Unknown category: {request.category}"
                )
                return

            limit = request.limit if request.limit > 0 else 20
            offset = request.offset if request.offset >= 0 else 0

            user_id = request.user_id if request.user_id > 0 else 0
            data = await app.services.list_provider.get_list(
                request.category, limit, offset, language=request.language or "en", user_id=user_id
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
        request: app.proto.recommendation_pb2.GetHomePageRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.HomePageResponse:
        try:
            user_id = request.user_id if request.user_id > 0 else 0
            force_personal_refresh = user_id > 0 and request.items_per_category == 0
            items_per_category = (
                request.items_per_category if request.items_per_category > 0 else 20
            )
            categories = await app.services.list_provider.get_home_page(
                items_per_category,
                user_id,
                personal_cache_only=user_id > 0 and not force_personal_refresh,
                force_personal_refresh=force_personal_refresh,
                language=request.language or "en",
            )
            response = app.proto.recommendation_pb2.HomePageResponse()
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
        request: app.proto.recommendation_pb2.GetAvailableCategoriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.AvailableCategoriesResponse:
        try:
            categories = app.services.list_provider.get_available_categories()
            response = app.proto.recommendation_pb2.AvailableCategoriesResponse()
            for cat in categories:
                response.categories.append(
                    app.proto.recommendation_pb2.CategoryInfo(
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
        request: app.proto.recommendation_pb2.RefreshRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.RefreshRecommendationsResponse:
        try:
            home_keys = [
                f"rec:{cat['key']}" for cat in app.services.list_builder.CATEGORIES
            ]
            deleted = await app.cache.delete_keys(*home_keys)
            await app.services.list_builder.refresh_all(app.db.async_session_maker)
            return app.proto.recommendation_pb2.RefreshRecommendationsResponse(
                success=True,
                message=f"Flushed {deleted} home cache keys, rebuilt home recommendation lists",
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")

    async def RefreshPersonalRecommendations(
        self,
        request: app.proto.recommendation_pb2.RefreshPersonalRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.RefreshPersonalRecommendationsResponse:
        try:
            deleted = await app.cache.delete_by_pattern("rec:profile:*")
            deleted += await app.cache.delete_by_pattern("rec:personal:*")
            await app.services.personal_refresher.refresh_all_personal(
                app.db.async_session_maker
            )
            return app.proto.recommendation_pb2.RefreshPersonalRecommendationsResponse(
                success=True,
                message=f"Flushed {deleted} personal cache keys, rebuilt personal recommendations",
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshPersonalRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")

    async def InvalidateUserRecommendations(
        self,
        request: app.proto.recommendation_pb2.InvalidateUserRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.InvalidateUserRecommendationsResponse:
        if not request.user_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id is required")
            return
        try:
            deleted = await app.cache.invalidate_user_personal_recommendations(
                request.user_id
            )
            return app.proto.recommendation_pb2.InvalidateUserRecommendationsResponse(
                success=True,
                deleted_keys=deleted,
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in InvalidateUserRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Invalidation failed: {str(e)}")

    async def RefreshUserPersonalRecommendations(
        self,
        request: app.proto.recommendation_pb2.RefreshUserPersonalRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.RefreshUserPersonalRecommendationsResponse:
        username = (request.username or "").strip()
        if not username:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "username is required"
            )
            return
        try:
            async with app.db.async_session_maker() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        "SELECT user_id FROM auth.users WHERE username = :username"
                    ),
                    {"username": username},
                )
                row = result.first()
            if not row:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND, f"User '{username}' not found"
                )
                return
            user_id = int(row.user_id)
            deleted = await app.cache.invalidate_user_personal_recommendations(user_id)
            await app.services.personal_refresher.refresh_user_personal(
                app.db.async_session_maker, user_id
            )
            return app.proto.recommendation_pb2.RefreshUserPersonalRecommendationsResponse(
                success=True,
                message=(
                    f"Flushed {deleted} cache keys for user '{username}' "
                    f"(id={user_id}), rebuilt personal recommendations"
                ),
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshUserPersonalRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")

    async def RefreshContextualRecommendations(
        self,
        request: app.proto.recommendation_pb2.RefreshContextualRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.RefreshContextualRecommendationsResponse:
        try:
            deleted = await app.cache.delete_by_pattern("rec:book:*")
            deleted += await app.cache.delete_by_pattern("rec:author:*")
            deleted += await app.cache.delete_by_pattern("rec:series:*")
            await app.services.contextual_precompute.refresh_contextual_recs(
                app.db.async_session_maker
            )
            return app.proto.recommendation_pb2.RefreshContextualRecommendationsResponse(
                success=True,
                message=f"Flushed {deleted} contextual cache keys, rebuilt contextual recommendations",
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshContextualRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")

    async def InvalidateContextualCache(
        self,
        request: app.proto.recommendation_pb2.InvalidateContextualCacheRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.InvalidateContextualCacheResponse:
        entity_type = (request.entity_type or "").strip().lower()
        slug = (request.slug or "").strip()
        if entity_type not in ("book", "author", "series"):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "entity_type must be 'book', 'author', or 'series'",
            )
            return
        if not slug:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "slug is required")
            return

        table_by_type = {
            "book": ("books", "book_id"),
            "author": ("authors", "author_id"),
            "series": ("series", "series_id"),
        }
        table, pk = table_by_type[entity_type]
        try:
            async with app.db.async_session_maker() as session:
                result = await session.execute(
                    sqlalchemy.text(
                        f"SELECT {pk} AS id FROM {table} WHERE slug = :slug"
                    ),
                    {"slug": slug},
                )
                row = result.first()
            if not row:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"{entity_type} with slug '{slug}' not found",
                )
                return
            entity_id = int(row.id)
            cache_key = f"rec:{entity_type}:{entity_id}"
            deleted = await app.cache.delete_keys(cache_key)
            return app.proto.recommendation_pb2.InvalidateContextualCacheResponse(
                success=True,
                message=(
                    f"Deleted {deleted} key for {entity_type} '{slug}' "
                    f"(id={entity_id}, key={cache_key})"
                ),
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in InvalidateContextualCache: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Invalidate failed: {str(e)}")

    async def RefreshBookOfTheWeek(
        self,
        request: app.proto.recommendation_pb2.RefreshBookOfTheWeekRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.RefreshBookOfTheWeekResponse:
        try:
            languages = app.services.book_of_week_builder.available_languages()
            keys = [
                app.services.book_of_week_builder.bow_pool_cache_key(lang)
                for lang in languages
            ]
            deleted = await app.cache.delete_keys(*keys)
            results = await app.services.book_of_week_builder.refresh_book_of_the_week(
                app.db.async_session_maker
            )
            built = {lang: len(pool) for lang, pool in results.items() if pool}
            if not built:
                return app.proto.recommendation_pb2.RefreshBookOfTheWeekResponse(
                    success=False,
                    message=f"Flushed {deleted} bow cache keys, no eligible candidates found",
                )
            summary = ", ".join(f"{lang}={count}" for lang, count in built.items())
            return app.proto.recommendation_pb2.RefreshBookOfTheWeekResponse(
                success=True,
                message=f"Flushed {deleted} bow cache keys, pools cached ({summary})",
            )
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshBookOfTheWeek: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Refresh failed: {str(e)}")

    async def GetBookRecommendations(
        self,
        request: app.proto.recommendation_pb2.GetBookRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.BookRecommendationsResponse:
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
            response = app.proto.recommendation_pb2.BookRecommendationsResponse(
                book_id=request.book_id
            )
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
        request: app.proto.recommendation_pb2.GetAuthorRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.AuthorRecommendationsResponse:
        try:
            limit = request.limit_per_section if request.limit_per_section > 0 else 15
            user_id = request.user_id if request.user_id > 0 else 0
            sections = (
                await app.services.contextual_provider.get_author_recommendations(
                    request.author_id, limit, user_id
                )
            )
            if sections is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Author with ID {request.author_id} not found",
                )
                return
            response = app.proto.recommendation_pb2.AuthorRecommendationsResponse(
                author_id=request.author_id
            )
            for section in sections:
                response.sections.append(_dict_to_section(section))
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetAuthorRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    async def GetSeriesRecommendations(
        self,
        request: app.proto.recommendation_pb2.GetSeriesRecommendationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.SeriesRecommendationsResponse:
        try:
            limit = request.limit_per_section if request.limit_per_section > 0 else 15
            sections = (
                await app.services.contextual_provider.get_series_recommendations(
                    request.series_id, limit
                )
            )
            if sections is None:
                await context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Series with ID {request.series_id} not found",
                )
                return
            response = app.proto.recommendation_pb2.SeriesRecommendationsResponse(
                series_id=request.series_id
            )
            for section in sections:
                response.sections.append(_dict_to_section(section))
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetSeriesRecommendations: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")

    async def GetBookOfTheWeek(
        self,
        request: app.proto.recommendation_pb2.GetBookOfTheWeekRequest,
        context: grpc.aio.ServicerContext,
    ) -> app.proto.recommendation_pb2.BookOfTheWeekResponse:
        try:
            language = request.language or "en"
            available = app.services.book_of_week_builder.available_languages()
            if language not in available:
                language = available[0]
            cache_key = app.services.book_of_week_builder.bow_pool_cache_key(language)
            pool = await app.cache.get_cached(cache_key)
            if not pool:
                pool = await app.services.book_of_week_builder.refresh_book_of_the_week_for_language(
                    app.db.async_session_maker, language
                )
            if not pool:
                await context.abort(
                    grpc.StatusCode.UNAVAILABLE, "Book of the week not yet available"
                )
                return
            book = pool[0]
            response = app.proto.recommendation_pb2.BookOfTheWeekResponse(
                book_id=book["book_id"],
                title=book["title"],
                slug=book["slug"],
                language=book["language"],
                primary_cover_url=book["primary_cover_url"],
                first_sentence=book["first_sentence"],
                weighted_avg_rating=book["weighted_avg_rating"],
                rating_count=book["rating_count"],
            )
            for a in book.get("authors", []):
                response.authors.append(
                    app.proto.recommendation_pb2.BookOfTheWeekAuthor(
                        author_id=a["author_id"],
                        name=a["name"],
                        slug=a["slug"],
                    )
                )
            for c in book.get("categories", []):
                response.categories.append(
                    app.proto.recommendation_pb2.BookOfTheWeekCategory(
                        genre_id=c["genre_id"],
                        name=c["name"],
                        slug=c["slug"],
                    )
                )
            return response
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetBookOfTheWeek: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Internal error: {str(e)}")
