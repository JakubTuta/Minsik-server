import typing

import app.config
import fastapi


def _normalize(raw: typing.Optional[str]) -> typing.Optional[str]:
    """Reduce a raw language tag (e.g. "pl-PL", "PL_pl") to its base subtag ("pl")."""
    if not raw:
        return None
    base = raw.strip().lower().replace("_", "-").split("-")[0][:10]
    return base or None


def _available_languages() -> typing.List[str]:
    raw = app.config.settings.available_languages or "en"
    languages = [lang.strip() for lang in raw.split(",") if lang.strip()]
    return languages or ["en"]


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
    # Every candidate is validated against AVAILABLE_LANGUAGES before use: an
    # unvalidated value (a stray region subtag, a typo, an arbitrary query
    # string) would otherwise mint its own Redis cache-key namespace
    # (book_slug:{slug}:{junk}, rec:{category}:{junk}, ...) and never match
    # b.language in any query, so it's worse than useless — fall through to
    # the next source instead of accepting it.
    available = _available_languages()

    candidate = _normalize(language)
    if candidate and candidate in available:
        return candidate

    # Lazy import: app.middleware.auth imports app.utils.cookies, which would
    # otherwise import this module back (app.utils package init) before this
    # module finishes loading — a circular import at module-load time. Safe
    # here since it only runs at request time, after all modules are loaded.
    import app.middleware.auth

    credentials = await app.middleware.auth._bearer_scheme(request)
    user = await app.middleware.auth.get_current_user_optional(request, credentials)
    candidate = _normalize(user.get("preferred_language")) if user else None
    if candidate and candidate in available:
        return candidate

    candidate = _normalize(request.cookies.get("pref_lang"))
    if candidate and candidate in available:
        return candidate

    accept_lang = request.headers.get("Accept-Language", "")
    if accept_lang:
        candidate = _normalize(accept_lang.split(",")[0].split(";")[0])
        if candidate and candidate in available:
            return candidate

    # Last resort is the first configured language rather than a literal "en":
    # a deployment whose AVAILABLE_LANGUAGES omits English would otherwise get
    # a code that matches no b.language row anywhere. Mirrors the same choice
    # in the recommendation service's gRPC server.
    return "en" if "en" in available else available[0]
