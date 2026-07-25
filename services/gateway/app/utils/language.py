import typing

import fastapi


async def resolve_language(
    request: fastapi.Request,
    language: typing.Optional[str] = fastapi.Query(
        None,
        min_length=2,
        max_length=10,
        description=(
            "Language code (e.g. en, pl, de). Overrides the signed-in user's "
            "saved preference, the pref_lang cookie, and browser language "
            "when provided."
        ),
    ),
) -> str:
    if language:
        return language

    # Lazy import: app.middleware.auth imports app.utils.cookies, which would
    # otherwise import this module back (app.utils package init) before this
    # module finishes loading — a circular import at module-load time. Safe
    # here since it only runs at request time, after all modules are loaded.
    import app.middleware.auth

    credentials = await app.middleware.auth._bearer_scheme(request)
    user = await app.middleware.auth.get_current_user_optional(request, credentials)
    if user and user.get("preferred_language"):
        return user["preferred_language"]

    cookie_lang = request.cookies.get("pref_lang")
    if cookie_lang:
        return cookie_lang

    accept_lang = request.headers.get("Accept-Language", "")
    if accept_lang:
        lang = accept_lang.split(",")[0].split(";")[0].strip()[:8]
        if lang:
            return lang

    return "en"
