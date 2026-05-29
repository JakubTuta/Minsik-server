import secrets

import fastapi
import starlette.middleware.base
import starlette.requests
import starlette.responses

import app.utils.cookies

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/google",
}


class CSRFMiddleware(starlette.middleware.base.BaseHTTPMiddleware):
    async def dispatch(self, request: starlette.requests.Request, call_next):
        if request.method in _UNSAFE_METHODS and request.url.path not in _EXEMPT_PATHS:
            access_cookie = request.cookies.get(app.utils.cookies.ACCESS_COOKIE)
            if access_cookie:
                header_token = request.headers.get("X-CSRF-Token")
                cookie_token = request.cookies.get(app.utils.cookies.CSRF_COOKIE)
                if not header_token or not cookie_token or not secrets.compare_digest(header_token, cookie_token):
                    return starlette.responses.JSONResponse(
                        status_code=403,
                        content={
                            "success": False,
                            "data": None,
                            "error": {
                                "code": "CSRF_FAILED",
                                "message": "CSRF token missing or invalid",
                                "details": {},
                            },
                        },
                    )

        return await call_next(request)


def setup_csrf(app: fastapi.FastAPI) -> None:
    app.add_middleware(CSRFMiddleware)
