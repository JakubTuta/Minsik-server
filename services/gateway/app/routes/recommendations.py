import logging
import typing

import app.config
import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit
import app.models.recommendation_responses
import app.utils.language
import app.utils.responses
import fastapi
import grpc

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(prefix="/api/v1", tags=["Recommendations"])
admin_router = fastapi.APIRouter(prefix="/api/v1/admin", tags=["Admin"])

limiter = app.middleware.rate_limit.limiter

_to_section_dict = app.utils.responses.recommendation_section_to_dict


@router.get(
    "/recommendations/home",
    response_model=app.models.recommendation_responses.HomePageResponse,
    summary="Get home page recommendations",
    description="""
    Returns generic pre-computed recommendation sections for the home page.

    Sections are built nightly at midnight and served from Redis cache (24h TTL).
    The set of returned sections is configured via `HOME_BOOK_CATEGORIES` and
    `HOME_AUTHOR_CATEGORIES` environment variables.

    **Item types:**
    - `book`: Contains `book_items` with title, slug, cover, authors, rating, and score
    - `author`: Contains `author_items` with name, slug, photo, book count, and score

    For personalized sections interleaved with these, use
    `GET /api/v1/users/me/recommendations/home` (authentication required).

    Returns `503` if the cache has not been populated yet.
    """,
    responses={
        503: {"description": "Recommendations not yet available (cache empty)"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_home_page(
    request: fastapi.Request,
    items_per_category: int = fastapi.Query(
        20, ge=1, le=100, description="Number of items to return per section"
    ),
    lang: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_home_page(
            items_per_category=items_per_category, language=lang
        )
        sections = [_to_section_dict(cat.category, cat) for cat in response.categories]
        return app.utils.responses.success_response({"sections": sections})
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "in get_home_page", e)
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            return app.utils.responses.error_response(
                "UNAVAILABLE", "Recommendations not yet available", status_code=503
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_home_page: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/categories",
    response_model=app.models.recommendation_responses.AvailableCategoriesResponse,
    summary="Get available recommendation categories",
    description="""
    Returns the static list of all recommendation categories defined in the service.

    Each entry includes:
    - `key`: The identifier used in other endpoints (e.g. `most_read`)
    - `display_name`: Human-readable label (e.g. `Most Read Books`)
    - `item_type`: Either `book` or `author`

    This endpoint does not depend on cache state and always returns the full registry.
    """,
    responses={
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_available_categories(request: fastapi.Request):
    try:
        response = (
            await app.grpc_clients.recommendation_client.get_available_categories()
        )
        categories = [
            {
                "key": cat.category,
                "display_name": cat.display_name,
                "item_type": cat.item_type,
            }
            for cat in response.categories
        ]
        return app.utils.responses.success_response({"categories": categories})
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in get_available_categories: {e.code()} - {e.details()}"
        )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch categories", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_available_categories: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/book-of-the-week",
    response_model=app.models.recommendation_responses.BookOfTheWeekResponse,
    summary="Get book of the week",
    description="""
    Returns the curated book of the week.

    Selected every Monday at 03:00 UTC. Cached for 7 days with history tracking
    to ensure a different book is picked each week (last 12 weeks excluded).

    Eligibility criteria: has cover image, first sentence, at least 1 author and
    1 genre, weighted average rating >= 4.0, total rating count >= 100, language = en.

    Returns `503` if not yet populated (e.g. first startup before Monday).
    """,
    responses={
        503: {"description": "Book of the week not yet available"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_book_of_the_week(
    request: fastapi.Request,
    lang: str = fastapi.Depends(app.utils.language.resolve_language),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_book_of_the_week(language=lang)
        data = {
            "book_id": response.book_id,
            "title": response.title,
            "slug": response.slug,
            "language": response.language,
            "primary_cover_url": response.primary_cover_url,
            "first_sentence": response.first_sentence,
            "weighted_avg_rating": response.weighted_avg_rating,
            "rating_count": response.rating_count,
            "authors": [
                {"author_id": a.author_id, "name": a.name, "slug": a.slug}
                for a in response.authors
            ],
            "categories": [
                {"genre_id": c.genre_id, "name": c.name, "slug": c.slug}
                for c in response.categories
            ],
        }
        return app.utils.responses.success_response(data)
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "in get_book_of_the_week", e)
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            return app.utils.responses.error_response(
                "UNAVAILABLE", "Book of the week not yet available", status_code=503
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch book of the week", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_book_of_the_week: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/{category}",
    response_model=app.models.recommendation_responses.RecommendationSectionResponse,
    summary="Get a single recommendation section",
    description="""
    Returns a paginated recommendation section for the given category key.

    **Available category keys** (see `/recommendations/categories` for display names):

    Book sections: `most_read`, `most_wanted`, `trending_reads`, `most_viewed`,
    `highest_rated`, `community_top_rated`, `most_rated`, `recently_added`,
    `classics`, `user_favorites`, `recently_finished`, `currently_reading`,
    `best_writing`, `most_emotional`, `funniest`, `most_thought_provoking`,
    `most_rereadable`

    Author sections: `top_authors`, `popular_authors`

    **Pagination:** `total` reflects the full cached list size (before pagination).

    **Score field:** The `score` value represents the ranking signal used to order
    the section (e.g. `ol_already_read_count` for `most_read`, `avg_rating` for
    `highest_rated`, sub-rating average for `best_writing`).
    """,
    responses={
        404: {"description": "Unknown category key"},
        503: {"description": "Recommendations not yet available (cache empty)"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_recommendation_list(
    request: fastapi.Request,
    category: str = fastapi.Path(
        ..., description="Category key (e.g. 'most_read', 'top_authors')"
    ),
    limit: int = fastapi.Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = fastapi.Query(0, ge=0, description="Pagination offset"),
    lang: str = fastapi.Depends(app.utils.language.resolve_language),
    current_user: typing.Optional[typing.Dict[str, typing.Any]] = fastapi.Depends(
        app.middleware.auth.get_current_user_optional
    ),
):
    try:
        user_id = current_user["user_id"] if current_user else 0
        response = await app.grpc_clients.recommendation_client.get_recommendation_list(
            category=category, limit=limit, offset=offset, language=lang, user_id=user_id
        )
        return app.utils.responses.success_response(
            _to_section_dict(response.category, response)
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in get_recommendation_list: {e.code()} - {e.details()}"
        )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Unknown category: {category}", status_code=404
            )
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            return app.utils.responses.error_response(
                "UNAVAILABLE", "Recommendations not yet available", status_code=503
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch recommendation section", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_recommendation_list: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/book/{book_id}",
    response_model=app.models.recommendation_responses.BookRecommendationsResponse,
    summary="Get recommendations for a book",
    description="""
    Returns generic contextual recommendation sections for a specific book.

    Sections (only non-empty sections are returned):
    - `more_by_author` — Other books by the same author(s), ordered by avg_rating
    - `more_from_series` — Other books in the same series ordered by series_position (if applicable)
    - `similar_by_genre` — Books with the highest Jaccard genre overlap
    - `readers_also_enjoyed` — Books co-read by users who read this book (500-reader cap)
    - `similar_{dimension}` — Books scoring within 0.5 of this book's most prominent
      sub-rating dimension (e.g. `similar_humor`, `similar_writing_quality`)

    Results are computed on first request and cached for 1 hour.

    For the personalized `you_might_like` section and read-book filtering, use
    `GET /api/v1/users/me/recommendations/book/{book_id}` (authentication required).
    """,
    responses={
        404: {"description": "Book not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_book_recommendations(
    request: fastapi.Request,
    book_id: int = fastapi.Path(..., description="Book ID"),
    limit_per_section: int = fastapi.Query(
        15, ge=1, le=50, description="Number of items per recommendation section"
    ),
):
    try:
        response = (
            await app.grpc_clients.recommendation_client.get_book_recommendations(
                book_id=book_id, limit_per_section=limit_per_section
            )
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response(
            {"book_id": response.book_id, "sections": sections}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in get_book_recommendations: {e.code()} - {e.details()}"
        )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Book with ID {book_id} not found", status_code=404
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch book recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_book_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/author/{author_id}",
    response_model=app.models.recommendation_responses.AuthorRecommendationsResponse,
    summary="Get recommendations for an author",
    description="""
    Returns generic contextual recommendation sections for a specific author.

    Sections (only non-empty sections are returned):
    - `similar_authors` — Authors with the highest Jaccard genre overlap across their books
    - `fans_also_read` — Authors co-read by fans of this author (500-reader cap)

    Results are computed on first request and cached for 1 hour.

    For the personalized `unread_by_author` section, use
    `GET /api/v1/users/me/recommendations/author/{author_id}` (authentication required).
    """,
    responses={
        404: {"description": "Author not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_author_recommendations(
    request: fastapi.Request,
    author_id: int = fastapi.Path(..., description="Author ID"),
    limit_per_section: int = fastapi.Query(
        15, ge=1, le=50, description="Number of items per recommendation section"
    ),
):
    try:
        response = (
            await app.grpc_clients.recommendation_client.get_author_recommendations(
                author_id=author_id, limit_per_section=limit_per_section
            )
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response(
            {"author_id": response.author_id, "sections": sections}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in get_author_recommendations: {e.code()} - {e.details()}"
        )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Author with ID {author_id} not found", status_code=404
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch author recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_author_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/series/{series_id}",
    response_model=app.models.recommendation_responses.SeriesRecommendationsResponse,
    summary="Get recommendations for a series",
    description="""
    Returns contextual recommendation sections for a specific series.

    Sections (only non-empty sections are returned):
    - `more_by_author` — Other books by the series author(s), ordered by avg_rating
    - `similar_by_genre` — Books with the highest Jaccard genre overlap to the series
    - `readers_also_enjoyed` — Books co-read by users who read books from this series

    Results are computed on first request and cached for 1 hour.
    """,
    responses={
        404: {"description": "Series not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_series_recommendations(
    request: fastapi.Request,
    series_id: int = fastapi.Path(..., description="Series ID"),
    limit_per_section: int = fastapi.Query(
        15, ge=1, le=50, description="Number of items per recommendation section"
    ),
):
    try:
        response = (
            await app.grpc_clients.recommendation_client.get_series_recommendations(
                series_id=series_id, limit_per_section=limit_per_section
            )
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response(
            {"series_id": response.series_id, "sections": sections}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in get_series_recommendations: {e.code()} - {e.details()}"
        )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Series with ID {series_id} not found", status_code=404
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch series recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_series_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/refresh",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Flush home cache and rebuild home lists",
    description="""
    Triggers an immediate synchronous rebuild of home recommendation lists:

    1. Flushes `rec:{category}` cache keys for each known home category.
    2. Re-runs the home recommendation list builder (writes lists with 24h TTL).

    Does not touch personal recs, contextual recs, or the book of the week — each has its own endpoint.

    Requires a valid JWT with `role=admin`. May take several seconds.
    """,
    dependencies=[fastapi.Depends(app.middleware.auth.require_admin)],
    responses={
        403: {"description": "Admin role required"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def refresh_recommendations(request: fastapi.Request):
    try:
        response = (
            await app.grpc_clients.recommendation_client.refresh_recommendations()
        )
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in refresh_recommendations: {e.code()} - {e.details()}"
        )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to refresh recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in refresh_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/personal/refresh",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Flush personal cache and rebuild personal recommendations",
    description="""
    Triggers an immediate synchronous rebuild of personal recommendation state:

    1. Deletes all `rec:profile:*` and `rec:personal:*` Redis keys.
    2. Re-runs the personal refresher for active users.

    Requires a valid JWT with `role=admin`.
    """,
    dependencies=[fastapi.Depends(app.middleware.auth.require_admin)],
    responses={
        403: {"description": "Admin role required"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def refresh_personal_recommendations(request: fastapi.Request):
    try:
        response = (
            await app.grpc_clients.recommendation_client.refresh_personal_recommendations()
        )
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in refresh_personal_recommendations: {e.code()} - {e.details()}"
        )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to refresh personal recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in refresh_personal_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/personal/refresh/{username}",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Flush personal cache and rebuild for a single user",
    description="""
    Triggers an immediate synchronous rebuild of one user's personal recommendation state:

    1. Deletes the user's `rec:profile:{user_id}`, `rec:personal:{user_id}`,
       `rec:personal:book:{user_id}:*`, and `rec:personal:author:{user_id}:*` keys.
    2. Re-runs the personal refresher for that user only.

    Requires a valid JWT with `role=admin`.
    """,
    dependencies=[fastapi.Depends(app.middleware.auth.require_admin)],
    responses={
        403: {"description": "Admin role required"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def refresh_user_personal_recommendations(
    request: fastapi.Request,
    username: str = fastapi.Path(..., description="Username (nickname) of the user"),
):
    try:
        response = (
            await app.grpc_clients.recommendation_client.refresh_user_personal_recommendations(
                username=username,
            )
        )
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in refresh_user_personal_recommendations: {e.code()} - {e.details()}"
        )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"User '{username}' not found", status_code=404
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            return app.utils.responses.error_response(
                "INVALID_ARGUMENT", e.details(), status_code=400
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR",
            "Failed to refresh personal recommendations for user",
            status_code=500,
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in refresh_user_personal_recommendations: {str(e)}"
        )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/contextual/refresh",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Flush contextual cache and rebuild contextual recommendations",
    description="""
    Triggers an immediate synchronous rebuild of contextual recommendation state:

    1. Deletes all `rec:book:*`, `rec:author:*`, and `rec:series:*` Redis keys.
    2. Re-runs the contextual precompute job.

    Requires a valid JWT with `role=admin`.
    """,
    dependencies=[fastapi.Depends(app.middleware.auth.require_admin)],
    responses={
        403: {"description": "Admin role required"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def refresh_contextual_recommendations(request: fastapi.Request):
    try:
        response = (
            await app.grpc_clients.recommendation_client.refresh_contextual_recommendations()
        )
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in refresh_contextual_recommendations: {e.code()} - {e.details()}"
        )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to refresh contextual recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in refresh_contextual_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/contextual/invalidate/{entity_type}/{slug}",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Invalidate contextual cache for a single book/author/series",
    description="""
    Deletes the cached contextual recommendation entry for a single entity. The
    cache will be lazily rebuilt on the next request.

    `entity_type` must be one of: `book`, `author`, `series`.

    Requires a valid JWT with `role=admin`.
    """,
    dependencies=[fastapi.Depends(app.middleware.auth.require_admin)],
    responses={
        400: {"description": "Invalid entity_type or slug"},
        403: {"description": "Admin role required"},
        404: {"description": "Entity not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def invalidate_contextual_cache(
    request: fastapi.Request,
    entity_type: str = fastapi.Path(
        ..., description="Entity type: book | author | series"
    ),
    slug: str = fastapi.Path(..., description="Entity slug"),
):
    try:
        response = (
            await app.grpc_clients.recommendation_client.invalidate_contextual_cache(
                entity_type=entity_type,
                slug=slug,
            )
        )
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in invalidate_contextual_cache: {e.code()} - {e.details()}"
        )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", e.details(), status_code=404
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            return app.utils.responses.error_response(
                "INVALID_ARGUMENT", e.details(), status_code=400
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR",
            "Failed to invalidate contextual cache",
            status_code=500,
        )
    except Exception as e:
        logger.error(f"Unexpected error in invalidate_contextual_cache: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/book-of-the-week/refresh",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Flush book-of-the-week cache and re-select",
    description="""
    Triggers an immediate synchronous refresh of the book of the week:

    1. Deletes the `bow:current` Redis key.
    2. Re-runs the selection logic and caches the new pick (7d TTL).

    Does not touch home recommendation lists.

    Requires a valid JWT with `role=admin`.
    """,
    dependencies=[fastapi.Depends(app.middleware.auth.require_admin)],
    responses={
        403: {"description": "Admin role required"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def refresh_book_of_the_week(request: fastapi.Request):
    try:
        response = (
            await app.grpc_clients.recommendation_client.refresh_book_of_the_week()
        )
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(
            f"gRPC error in refresh_book_of_the_week: {e.code()} - {e.details()}"
        )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to refresh book of the week", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in refresh_book_of_the_week: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )
