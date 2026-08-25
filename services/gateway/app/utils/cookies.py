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


def _cookie_kwargs(
    max_age: int, path: str, http_only: bool, shared_domain: bool
) -> typing.Dict[str, typing.Any]:
    kwargs: typing.Dict[str, typing.Any] = {
        "max_age": max_age,
        "path": path,
        "httponly": http_only,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
    }
    if shared_domain and settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def _delete_kwargs(path: str, domain: typing.Optional[str]) -> typing.Dict[str, typing.Any]:
    kwargs: typing.Dict[str, typing.Any] = {
        "path": path,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
    }
    if domain:
        kwargs["domain"] = domain
    return kwargs


def set_auth_cookies(
    response: fastapi.Response,
    access_token: str,
    refresh_token: str,
    csrf_token: typing.Optional[str] = None,
) -> str:
    """Write the session cookies, scoping each one as narrowly as it allows.

    The two bearer cookies are host-only: nothing but this API ever presents
    them, and a `Domain=.example.tld` would hand a live session to every
    sibling subdomain. Only the CSRF token needs the parent domain, because
    the frontend reads it from JavaScript on its own origin — and it is a
    value the double-submit check compares against itself, not a credential.
    """
    access_max_age = settings.jwt_access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 24 * 60 * 60

    if csrf_token is None:
        csrf_token = generate_csrf_token()

    # Sessions issued before the bearer cookies became host-only still carry a
    # domain-scoped copy that the browser would keep sending alongside the new
    # one. Dropping it here means one login converts a stale session.
    if settings.cookie_domain:
        response.delete_cookie(
            ACCESS_COOKIE, **_delete_kwargs("/", settings.cookie_domain)
        )
        response.delete_cookie(
            REFRESH_COOKIE,
            **_delete_kwargs(REFRESH_COOKIE_PATH, settings.cookie_domain),
        )

    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        **_cookie_kwargs(access_max_age, "/", True, shared_domain=False),
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        **_cookie_kwargs(refresh_max_age, REFRESH_COOKIE_PATH, True, shared_domain=False),
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        **_cookie_kwargs(refresh_max_age, "/", False, shared_domain=True),
    )

    return csrf_token


def clear_auth_cookies(response: fastapi.Response) -> None:
    # Both scopes for the bearer cookies: a session predating the host-only
    # switch is only logged out if its domain-scoped copy is cleared too.
    domains: typing.Tuple[typing.Optional[str], ...] = (None,)
    if settings.cookie_domain:
        domains = (None, settings.cookie_domain)

    for domain in domains:
        response.delete_cookie(ACCESS_COOKIE, **_delete_kwargs("/", domain))
        response.delete_cookie(
            REFRESH_COOKIE, **_delete_kwargs(REFRESH_COOKIE_PATH, domain)
        )

    response.delete_cookie(
        CSRF_COOKIE, **_delete_kwargs("/", settings.cookie_domain or None)
    )
