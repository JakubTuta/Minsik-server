import asyncio
import datetime
import typing

import app.config
import app.grpc_clients
import app.middleware.rate_limit
import app.models.responses
import fastapi
import grpc

router = fastapi.APIRouter(prefix="/health", tags=["Health"])

limiter = app.middleware.rate_limit.limiter

_DEPENDENCIES: typing.Tuple[typing.Tuple[str, typing.Any], ...] = (
    ("ingestion_service", app.grpc_clients.ingestion_client),
    ("books_service", app.grpc_clients.books_client),
    ("auth_service", app.grpc_clients.auth_client),
    ("user_data_service", app.grpc_clients.user_data_client),
    ("recommendation_service", app.grpc_clients.recommendation_client),
)


async def _probe(client: typing.Any) -> str:
    try:
        return "healthy" if await client.health_check() else "unhealthy"
    except grpc.RpcError:
        return "unhealthy"
    except Exception as e:
        return f"error: {str(e)}"


@router.get(
    "",
    response_model=app.models.responses.HealthResponse,
    summary="Basic health check",
    description="Returns basic health status of the gateway service",
    dependencies=[fastapi.Depends(lambda: limiter)],
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def health(request: fastapi.Request):
    return app.models.responses.HealthResponse(
        status="healthy",
        service="gateway",
        version="1.0.0",
        timestamp=datetime.datetime.now().isoformat(),
    )


@router.get(
    "/deep",
    response_model=app.models.responses.DeepHealthResponse,
    summary="Deep health check",
    description="Returns health status of gateway and all dependent services",
    dependencies=[fastapi.Depends(lambda: limiter)],
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def deep_health(request: fastapi.Request):
    # Probed concurrently: serially, five unreachable services would each burn
    # the full timeout and the check itself would look like the outage.
    results = await asyncio.gather(
        *(_probe(client) for _, client in _DEPENDENCIES)
    )
    dependencies = {
        name: result for (name, _), result in zip(_DEPENDENCIES, results)
    }

    overall_status = (
        "healthy" if all(v == "healthy" for v in dependencies.values()) else "degraded"
    )

    return app.models.responses.DeepHealthResponse(
        status=overall_status,
        service="gateway",
        version="1.0.0",
        timestamp=datetime.datetime.now().isoformat(),
        dependencies=dependencies,
    )
