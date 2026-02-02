import datetime
import fastapi
import grpc
import app.config
import app.models.responses
import app.grpc_clients
import app.middleware.rate_limit

router = fastapi.APIRouter(prefix="/health", tags=["Health"])

limiter = app.middleware.rate_limit.limiter


@router.get(
    "",
    response_model=app.models.responses.HealthResponse,
    summary="Basic health check",
    description="Returns basic health status of the gateway service",
    dependencies=[fastapi.Depends(lambda: limiter)]
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def health(request: fastapi.Request):
    return app.models.responses.HealthResponse(
        status="healthy",
        service="gateway",
        version="1.0.0",
        timestamp=datetime.datetime.now().isoformat()
    )


@router.get(
    "/deep",
    response_model=app.models.responses.DeepHealthResponse,
    summary="Deep health check",
    description="Returns health status of gateway and all dependent services",
    dependencies=[fastapi.Depends(lambda: limiter)]
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def deep_health(request: fastapi.Request):
    dependencies = {}

    try:
        async with app.grpc_clients.IngestionClient() as client:
            await client.stub.GetIngestionStatus(
                app.proto.ingestion_pb2.GetIngestionStatusRequest(job_id="health-check"),
                timeout=2.0
            )
        dependencies["ingestion_service"] = "healthy"
    except grpc.RpcError:
        dependencies["ingestion_service"] = "unhealthy"
    except Exception as e:
        dependencies["ingestion_service"] = f"error: {str(e)}"

    overall_status = "healthy" if all(v == "healthy" for v in dependencies.values()) else "degraded"

    return app.models.responses.DeepHealthResponse(
        status=overall_status,
        service="gateway",
        version="1.0.0",
        timestamp=datetime.datetime.now().isoformat(),
        dependencies=dependencies
    )
