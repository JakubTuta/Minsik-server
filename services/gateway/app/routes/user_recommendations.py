import logging
import typing

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

router = fastapi.APIRouter(prefix="/api/v1/users/me", tags=["User Recommendations"])

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
    summary="Get personalized home page recommendations",
    description="""
    Returns personalized recommendation sections for the authenticated user.

    Sections (only non-empty sections are returned):
    - `for_you` — 60% genre affinity + 25% collaborative filtering (200 similar users) + 15% avg_rating
    - `because_you_liked` — seeded from user's highest-rated book (Jaccard genre + collaborative, 50/50)
    - `continue_series` — next unread books from in-progress series, ordered by series_position
    - `from_favorite_authors` — unread books by authors the user has previously read
    - `top_in_your_genres` — highest-rated books in the user's top genre, excluding read books
    - `want_to_read_picks` — want-to-read shelf re-ranked by avg_rating + community signals
    - `readers_like_you` — top books from 200 users with highest shelf overlap
    - `hidden_gems` — low-visibility books (rating_count < 20, view_count < 500) matching user's genres

    Returns an empty `sections` list for cold-start users (fewer than 5 shelved books).

    For generic (non-personalized) sections, use `GET /api/v1/recommendations/home`.
    """,
    responses={
        401: {"description": "Authentication required"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_personal_home_page(
    request: fastapi.Request,
    items_per_category: int = Query(20, ge=1, le=100, description="Number of items to return per section"),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user),
):
    user_id = current_user["user_id"]
    try:
        response = await app.grpc_clients.recommendation_client.get_home_page(
            items_per_category=items_per_category, user_id=user_id
        )
        sections = [_to_section_dict(cat.category, cat) for cat in response.categories]
        return app.utils.responses.success_response({"sections": sections})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_personal_home_page: {e.code()} - {e.details()}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch personalized recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_personal_home_page: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/book/{book_id}",
    response_model=app.models.recommendation_responses.BookRecommendationsResponse,
    summary="Get personalized recommendations for a book",
    description="""
    Returns the personalized recommendation section for a specific book page.

    Section returned (empty list if cold-start or no matches):
    - `you_might_like` — genre-affinity + collaborative filtering seeded from this book's genres,
      excluding the user's already-read books and the current book

    For generic contextual sections (more_by_author, similar_by_genre, etc.), use
    `GET /api/v1/recommendations/book/{book_id}`.
    """,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Book not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_personal_book_recommendations(
    request: fastapi.Request,
    book_id: int = fastapi.Path(..., description="Book ID"),
    limit_per_section: int = Query(15, ge=1, le=50, description="Number of items per section"),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user),
):
    user_id = current_user["user_id"]
    try:
        response = await app.grpc_clients.recommendation_client.get_book_recommendations(
            book_id=book_id, limit_per_section=limit_per_section, user_id=user_id
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response({"book_id": response.book_id, "sections": sections})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_personal_book_recommendations: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Book with ID {book_id} not found", status_code=404
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch personalized book recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_personal_book_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )


@router.get(
    "/recommendations/author/{author_id}",
    response_model=app.models.recommendation_responses.AuthorRecommendationsResponse,
    summary="Get personalized recommendations for an author",
    description="""
    Returns the personalized recommendation section for a specific author page.

    Section returned (empty list if cold-start or no matches):
    - `unread_by_author` — This author's books not yet on the user's shelves
      (neither read nor want-to-read), ordered by avg_rating

    For generic contextual sections (similar_authors, fans_also_read), use
    `GET /api/v1/recommendations/author/{author_id}`.
    """,
    responses={
        401: {"description": "Authentication required"},
        404: {"description": "Author not found"},
        500: {"description": "Internal server error"},
    },
)
@limiter.limit(f"{app.config.settings.rate_limit_per_minute}/minute")
async def get_personal_author_recommendations(
    request: fastapi.Request,
    author_id: int = fastapi.Path(..., description="Author ID"),
    limit_per_section: int = Query(15, ge=1, le=50, description="Number of items per section"),
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user),
):
    user_id = current_user["user_id"]
    try:
        response = await app.grpc_clients.recommendation_client.get_author_recommendations(
            author_id=author_id, limit_per_section=limit_per_section, user_id=user_id
        )
        sections = [_to_section_dict(s.section_key, s) for s in response.sections]
        return app.utils.responses.success_response({"author_id": response.author_id, "sections": sections})
    except grpc.RpcError as e:
        logger.error(f"gRPC error in get_personal_author_recommendations: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                "NOT_FOUND", f"Author with ID {author_id} not found", status_code=404
            )
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "Failed to fetch personalized author recommendations", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error in get_personal_author_recommendations: {str(e)}")
        return app.utils.responses.error_response(
            "INTERNAL_ERROR", "An unexpected error occurred", status_code=500
        )
