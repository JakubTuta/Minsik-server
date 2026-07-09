import contextlib
import logging
import signal
import sys

import app.config
import app.grpc_clients
import app.middleware
import app.middleware.cors
import app.middleware.csrf
import app.middleware.logging
import app.middleware.rate_limit
import app.tracing
import app.routes.admin
import app.routes.auth
import app.routes.books
import app.routes.categories
import app.routes.health
import app.routes.recommendations
import app.routes.sitemap
import app.routes.user_data
import app.routes.user_recommendations
import fastapi
import ledger.integrations.fastapi
import slowapi
import slowapi.errors
import slowapi.middleware
import uvicorn

settings = app.config.settings
health_router = app.routes.health.router
admin_router = app.routes.admin.router
auth_router = app.routes.auth.router
books_router = app.routes.books.router
user_data_router = app.routes.user_data.router
categories_router = app.routes.categories.router
recommendations_router = app.routes.recommendations.router
sitemap_router = app.routes.sitemap.router
recommendations_admin_router = app.routes.recommendations.admin_router
user_recommendations_router = app.routes.user_recommendations.router
grpc_clients_module = app.grpc_clients
tracing_module = app.tracing
limiter = app.middleware.rate_limit.limiter
_setup_cors = app.middleware.cors.setup_cors
_setup_csrf = app.middleware.csrf.setup_csrf
_setup_logging = app.middleware.logging.setup_logging_middleware

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    logger.info("Starting Gateway service...")
    await grpc_clients_module.ingestion_client.connect()
    await grpc_clients_module.books_client.connect()
    await grpc_clients_module.auth_client.connect()
    await grpc_clients_module.user_data_client.connect()
    await grpc_clients_module.recommendation_client.connect()
    logger.info("Gateway service started successfully")

    yield

    logger.info("Shutting down Gateway service...")
    await grpc_clients_module.recommendation_client.close()
    await grpc_clients_module.user_data_client.close()
    await grpc_clients_module.auth_client.close()
    await grpc_clients_module.books_client.close()
    await grpc_clients_module.ingestion_client.close()

    await tracing_module.shutdown()

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
    - User authentication (register, login, token refresh, profile)
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
        "url": "https://github.com/JakubTuta/Minsik-server",
        "email": "jakubtutka02@gmail.com",
    },
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    lifespan=lifespan,
)

ledger_client = tracing_module.init_ledger()

if ledger_client:
    app.add_middleware(ledger.integrations.fastapi.LedgerMiddleware, ledger_client=ledger_client)

if settings.env == "development":
    _setup_cors(app)

_setup_csrf(app)
_setup_logging(app)

if settings.rate_limit_enabled:
    app.state.limiter = limiter
    app.add_exception_handler(slowapi.errors.RateLimitExceeded, slowapi._rate_limit_exceeded_handler)
    app.add_middleware(slowapi.middleware.SlowAPIMiddleware)

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(books_router)
app.include_router(categories_router)
app.include_router(user_data_router)
app.include_router(recommendations_router)
app.include_router(sitemap_router)
app.include_router(recommendations_admin_router)
app.include_router(user_recommendations_router)


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
        access_log=True,
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxy_ips_list,
    )
