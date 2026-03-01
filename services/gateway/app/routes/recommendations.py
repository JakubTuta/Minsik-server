import logging

import app.config
import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit
import app.models.recommendation_responses
import app.utils.responses
import fastapi
import grpc
from fastapi import Query

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(prefix="/api/v1", tags=["Recommendations"])
admin_router = fastapi.APIRouter(prefix="/api/v1/admin", tags=["Admin"])

limiter = app.middleware.rate_limit.limiter


def _list_response_to_dict(response) -> dict:
    item_type = response.item_type
    items_key = "book_items" if item_type == "book" else "author_items"

    if item_type == "book":
        items = [
            {
                "book_id": item.book_id,
                "title": item.title,
                "slug": item.slug,
                "language": item.language,
                "primary_cover_url": item.primary_cover_url or None,
                "author_names": list(item.author_names),
                "author_slugs": list(item.author_slugs),
                "avg_rating": item.avg_rating or None,
                "rating_count": item.rating_count,
                "score": item.score,
            }
            for item in response.book_items
        ]
    else:
        items = [
            {
                "author_id": item.author_id,
                "name": item.name,
                "slug": item.slug,
                "photo_url": item.photo_url or None,
                "book_count": item.book_count,
                "score": item.score,
            }
            for item in response.author_items
        ]

    return {
        "category": response.category,
        "display_name": response.display_name,
        "item_type": item_type,
        items_key: items,
        "total": response.total,
    }


@router.get(
    "/recommendations/home",
    response_model=app.models.recommendation_responses.HomePageResponse,
    summary="Get home page recommendations",
    description="""
    Returns multiple pre-computed recommendation lists for the home page.

    Each category entry includes ranked items (books or authors) up to
    `items_per_category` per category. Lists are built by a background job
    every 24 hours and served from Redis cache.

    The set of returned categories is configured via `HOME_BOOK_CATEGORIES`
    and `HOME_AUTHOR_CATEGORIES` environment variables.

    **Item types:**
    - `book`: Contains `book_items` with title, slug, cover, authors, rating, and score
    - `author`: Contains `author_items` with name, slug, photo, book count, and score

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
    items_per_category: int = Query(20, ge=1, le=100, description="Number of items to return per category"),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_home_page(
            items_per_category=items_per_category
        )
        categories = [_list_response_to_dict(cat) for cat in response.categories]
        return app.utils.responses.success_response({"categories": categories})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_home_page: {e.code()} - {e.details()}")
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
    Returns the static list of all 19 recommendation categories defined in the service.

    Each entry includes:
    - `category`: The key used in other endpoints (e.g. `most_read`)
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
        response = await app.grpc_clients.recommendation_client.get_available_categories()
        categories = [
            {
                "category": cat.category,
                "display_name": cat.display_name,
                "item_type": cat.item_type,
            }
            for cat in response.categories
        ]
        return app.utils.responses.success_response({"categories": categories})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_available_categories: {e.code()} - {e.details()}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch categories", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_available_categories: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/{category}",
    response_model=app.models.recommendation_responses.RecommendationListResponse,
    summary="Get a single recommendation list",
    description="""
    Returns a paginated recommendation list for the given category key.

    **Available category keys** (see `/recommendations/categories` for display names):

    Book lists: `most_read`, `most_wanted`, `trending_reads`, `most_viewed`,
    `highest_rated`, `community_top_rated`, `most_rated`, `recently_added`,
    `classics`, `user_favorites`, `recently_finished`, `currently_reading`,
    `best_writing`, `most_emotional`, `funniest`, `most_thought_provoking`,
    `most_rereadable`

    Author lists: `top_authors`, `popular_authors`

    **Pagination:** `total` reflects the full cached list size (before pagination).

    **Score field:** The `score` value represents the ranking signal used to order
    the list (e.g. `ol_already_read_count` for `most_read`, `avg_rating` for
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
    category: str = fastapi.Path(..., description="Category key (e.g. 'most_read', 'top_authors')"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_recommendation_list(
            category=category, limit=limit, offset=offset
        )
        return app.utils.responses.success_response(_list_response_to_dict(response))
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_recommendation_list: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Unknown category: {category}", status_code=404
            )
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            return app.utils.responses.error_response(
                "UNAVAILABLE", "Recommendations not yet available", status_code=503
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch recommendation list", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_recommendation_list: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@admin_router.post(
    "/recommendations/refresh",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Refresh recommendation lists",
    description="""
    Triggers an immediate synchronous refresh of all 19 recommendation lists.

    Runs all SQL queries, builds the ranked lists, and writes them to Redis
    with a 24h TTL. This replaces the next scheduled background run.

    **Use cases:**
    - Force a refresh after a large data import
    - Re-populate cache after a Redis flush

    Requires a valid JWT with `role=admin`. The operation may take several
    seconds depending on database size.
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
        response = await app.grpc_clients.recommendation_client.refresh_recommendations()
        return app.utils.responses.success_response(
            {"success": response.success, "message": response.message}
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error in refresh_recommendations: {e.code()} - {e.details()}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to refresh recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in refresh_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )
