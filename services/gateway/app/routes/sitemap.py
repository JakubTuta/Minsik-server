import logging

import app.grpc_clients
import app.models.books_responses
import app.utils.responses
import fastapi
import grpc

router = fastapi.APIRouter(prefix="/api/v1/sitemap", tags=["Sitemap"])
logger = logging.getLogger(__name__)


@router.get(
    "/slugs",
    response_model=app.models.books_responses.SitemapSlugsResponse,
    summary="List public slugs for sitemap generation",
    description="""
    Returns paginated slugs of public entities, ordered by popularity.
    Intended for sitemap generation by the frontend.

    **Entity options:**
    - `books` - book slugs ordered by readers count
    - `authors` - author slugs ordered by view count
    - `series` - series slugs ordered by view count

    `total_count` is populated only when `offset` is 0.

    **Examples:**
    - `/api/v1/sitemap/slugs?entity=books&limit=10000`
    - `/api/v1/sitemap/slugs?entity=authors&limit=10000&offset=10000`
    """,
)
async def list_sitemap_slugs(
    entity: str = fastapi.Query("books", regex="^(books|authors|series)$"),
    limit: int = fastapi.Query(1000, ge=1, le=10000),
    offset: int = fastapi.Query(0, ge=0),
):
    try:
        response = await app.grpc_clients.books_client.list_sitemap_slugs(
            entity=entity, limit=limit, offset=offset
        )
        items = [
            {"slug": item.slug, "updated_at": item.updated_at or None}
            for item in response.items
        ]
        return app.utils.responses.success_response(
            {"items": items, "total_count": response.total_count}
        )
    except grpc.RpcError as e:
        app.utils.responses.log_grpc_error(logger, "in list_sitemap_slugs", e)
        raise fastapi.HTTPException(status_code=500, detail="Failed to fetch sitemap slugs")
    except Exception as e:
        logger.error(f"Unexpected error in list_sitemap_slugs: {str(e)}")
        raise fastapi.HTTPException(status_code=500, detail="Failed to fetch sitemap slugs")
