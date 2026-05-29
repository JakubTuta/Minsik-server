import secrets
import typing

import fastapi

import app.config

settings = app.config.settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _cookie_kwargs(max_age: int, path: str, http_only: bool) -> typing.Dict[str, typing.Any]:
    kwargs: typing.Dict[str, typing.Any] = {
        "max_age": max_age,
        "path": path,
        "httponly": http_only,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def set_auth_cookies(
    response: fastapi.Response,
    access_token: str,
    refresh_token: str,
    csrf_token: typing.Optional[str] = None,
) -> str:
    access_max_age = settings.jwt_access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 24 * 60 * 60

    if csrf_token is None:
        csrf_token = generate_csrf_token()

    response.set_cookie(ACCESS_COOKIE, access_token, **_cookie_kwargs(access_max_age, "/", True))
    response.set_cookie(REFRESH_COOKIE, refresh_token, **_cookie_kwargs(refresh_max_age, REFRESH_COOKIE_PATH, True))
    response.set_cookie(CSRF_COOKIE, csrf_token, **_cookie_kwargs(refresh_max_age, "/", False))

    return csrf_token


def clear_auth_cookies(response: fastapi.Response) -> None:
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, REFRESH_COOKIE_PATH), (CSRF_COOKIE, "/")):
        kwargs: typing.Dict[str, typing.Any] = {
            "path": path,
            "secure": settings.cookie_secure,
            "samesite": settings.cookie_samesite,
        }
        if settings.cookie_domain:
            kwargs["domain"] = settings.cookie_domain
        response.delete_cookie(name, **kwargs)
