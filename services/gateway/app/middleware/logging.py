import time
import logging
import fastapi
import starlette.middleware.base

logger = logging.getLogger(__name__)


class LoggingMiddleware(starlette.middleware.base.BaseHTTPMiddleware):
    async def dispatch(self, request: fastapi.Request, call_next):
        start_time = time.time()

        logger.info(f"Request: {request.method} {request.url.path}")

        response = await call_next(request)

        process_time = time.time() - start_time
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"- Status: {response.status_code} - Duration: {process_time:.3f}s"
        )

        response.headers["X-Process-Time"] = str(process_time)

        return response


def setup_logging_middleware(app: fastapi.FastAPI):
    app.add_middleware(LoggingMiddleware)
