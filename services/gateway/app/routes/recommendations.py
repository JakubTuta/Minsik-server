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


def _to_section_dict(key: str, item) -> dict:
    item_type = item.item_type
    result = {
        "key": key,
        "display_name": item.display_name,
        "item_type": item_type,
        "total": item.total,
    }
    if item_type == "book":
        result["book_items"] = [
            {
                "book_id": i.book_id,
                "title": i.title,
                "slug": i.slug,
                "language": i.language,
                "primary_cover_url": i.primary_cover_url or None,
                "author_names": list(i.author_names),
                "author_slugs": list(i.author_slugs),
                "avg_rating": i.avg_rating or None,
                "rating_count": i.rating_count,
                "score": i.score,
            }
            for i in item.book_items
        ]
    else:
        result["author_items"] = [
            {
                "author_id": i.author_id,
                "name": i.name,
                "slug": i.slug,
                "photo_url": i.photo_url or None,
                "book_count": i.book_count,
                "score": i.score,
            }
            for i in item.author_items
        ]
    return result


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
    items_per_category: int = Query(20, ge=1, le=100, description="Number of items to return per section"),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_home_page(
            items_per_category=items_per_category
        )
        sections = [_to_section_dict(cat.category, cat) for cat in response.categories]
        return app.utils.responses.success_response({"sections": sections})
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
        response = await app.grpc_clients.recommendation_client.get_available_categories()
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
    category: str = fastapi.Path(..., description="Category key (e.g. 'most_read', 'top_authors')"),
    limit: int = Query(20, ge=1, le=100, description="Number of items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_recommendation_list(
            category=category, limit=limit, offset=offset
        )
        return app.utils.responses.success_response(_to_section_dict(response.category, response))
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
    limit_per_section: int = Query(15, ge=1, le=50, description="Number of items per recommendation section"),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_book_recommendations(
            book_id=book_id, limit_per_section=limit_per_section
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response({"book_id": response.book_id, "sections": sections})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_book_recommendations: {e.code()} - {e.details()}")
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
    limit_per_section: int = Query(15, ge=1, le=50, description="Number of items per recommendation section"),
):
    try:
        response = await app.grpc_clients.recommendation_client.get_author_recommendations(
            author_id=author_id, limit_per_section=limit_per_section
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response({"author_id": response.author_id, "sections": sections})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_author_recommendations: {e.code()} - {e.details()}")
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


@admin_router.post(
    "/recommendations/refresh",
    response_model=app.models.recommendation_responses.RefreshRecommendationsResponse,
    summary="Refresh recommendation lists",
    description="""
    Triggers an immediate synchronous refresh of all recommendation sections.

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
