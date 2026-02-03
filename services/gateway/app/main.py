import logging
import sys
import signal
import contextlib
import fastapi
import uvicorn
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import app.config
import app.routes.health
import app.routes.admin
import app.routes.books
import app.middleware.cors as cors_middleware
import app.middleware.logging as logging_middleware
import app.middleware.rate_limit as rate_limit_middleware
import app.grpc_clients

settings = app.config.settings
health_router = app.routes.health.router
admin_router = app.routes.admin.router
books_router = app.routes.books.router
grpc_clients_module = app.grpc_clients
limiter = rate_limit_middleware.limiter

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    logger.info("Starting Gateway service...")
    await grpc_clients_module.ingestion_client.connect()
    await grpc_clients_module.books_client.connect()
    logger.info("Gateway service started successfully")

    yield

    logger.info("Shutting down Gateway service...")
    await grpc_clients_module.books_client.close()
    await grpc_clients_module.ingestion_client.close()
    logger.info("Gateway service shut down successfully")


app = fastapi.FastAPI(
    title="Minsik Gateway API",
    description="""
    ## Minsik Gateway Service

    Single entry point for all client requests to the Minsik platform.

    ### Architecture

    - **REST API**: External clients communicate via REST
    - **gRPC**: Internal service communication
    - **Security**: JWT validation, rate limiting, CORS
    - **Network Isolation**: Only service exposed to public internet

    ### Features

    - Book ingestion management (admin)
    - Book catalog browsing and search
    - Author profiles and book listings
    - User authentication (coming soon)
    - Recommendations (coming soon)

    ### Admin Operations

    The admin endpoints allow triggering and monitoring background ingestion jobs:

    - **Trigger Ingestion**: Start importing books from Open Library and/or Google Books
    - **Check Status**: Monitor progress of running jobs
    - **Cancel Job**: Stop a running ingestion job
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Minsik Team",
        "url": "https://github.com/your-org/minsik",
        "email": "support@minsik.app"
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT"
    },
    lifespan=lifespan
)

if settings.env == "development":
    cors_middleware.setup_cors(app)

logging_middleware.setup_logging_middleware(app)

if settings.rate_limit_enabled:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(books_router)


def handle_shutdown(signum, frame):
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    uvicorn.run(
        "app.main:app",
        host=settings.gateway_host,
        port=settings.gateway_http_port,
        workers=settings.gateway_workers,
        log_level=settings.log_level.lower(),
        access_log=True
    )
