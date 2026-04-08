import logging

import app.grpc_clients
import app.models.books_responses
from fastapi import APIRouter, HTTPException, Query
from google.protobuf.json_format import MessageToDict

router = APIRouter(prefix="/api/v1/categories", tags=["Categories"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=app.models.books_responses.ListCategoriesResponse,
    summary="List all categories",
    description="""
    Get all available top-level categories.

    This endpoint returns the curated taxonomy of books available in the system,
    which maps OpenLibrary genres into clean categories like "Fantasy", "Romance", etc.

    Each category includes its slug and name.
    """,
)
async def list_categories():
    try:
        response = await app.grpc_clients.books_client.list_categories()
        return {"success": True, "data": {"categories": response.get("categories", [])}}
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch categories")


@router.get(
    "/{category_slug}",
    response_model=app.models.books_responses.CategoryResponse,
    summary="Get category details",
    description="""
    Get details of a specific category.

    **Examples:**
    - `/api/v1/categories/fantasy`
    - `/api/v1/categories/science-fiction`
    """,
)
async def get_category(
    category_slug: str,
):
    try:
        response = await app.grpc_clients.books_client.get_category(category_slug)
        return {"success": True, "data": response.get("category", {})}
    except Exception as e:
        logger.error(f"Error fetching category {category_slug}: {str(e)}")
        if "Category not found" in str(e):
            raise HTTPException(status_code=404, detail="Category not found")
        raise HTTPException(status_code=500, detail="Failed to fetch category")


@router.get(
    "/{category_slug}/books",
    response_model=app.models.books_responses.CategoryBooksResponse,
    summary="Get category books",
    description="""
    Get books for a specific category.

    The results are paginated and can be sorted by popularity or rating.
    By default, sorts by popularity descending.

    When `offset` is 0, results are served from a pre-populated Redis cache
    that refreshes every 24 hours, ensuring fast response times for the first page.

    **Sort Options (sort_by):**
    - `popularity` - Sorts by total number of readers/ratings (default)
    - `rating` - Sorts by average rating

    **Language Filter (`language`):**
    Filters book results to the specified language edition (default: `en`).

    **Examples:**
    - `/api/v1/categories/fantasy/books?limit=20`
    - `/api/v1/categories/romance/books?sort_by=rating&language=pl`
    """,
)
async def get_category_books(
    category_slug: str,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("popularity", regex="^(popularity|rating)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    language: str = Query(
        "en", description="ISO 639-1 language code (e.g., en, es, fr)"
    ),
):
    try:
        response = await app.grpc_clients.books_client.get_category_books(
            category_slug=category_slug,
            limit=limit,
            offset=offset,
            language=language,
            sort_by=sort_by,
            order=order,
        )

        response_dict = MessageToDict(response, preserving_proto_field_name=True)
        return {
            "success": True,
            "data": {
                "books": response_dict.get("books", []),
                "total_count": response_dict.get("total_count", 0),
            },
        }
    except Exception as e:
        logger.error(f"Error fetching books for category {category_slug}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch category books")
