import app.config
import slowapi
import slowapi.util


def get_limiter() -> slowapi.Limiter:
    kwargs = {
        "key_func": slowapi.util.get_remote_address,
        "default_limits": [f"{app.config.settings.rate_limit_per_minute}/minute"],
        "enabled": app.config.settings.rate_limit_enabled,
    }
    if app.config.settings.rate_limit_storage_uri:
        kwargs["storage_uri"] = app.config.settings.rate_limit_storage_uri
    return slowapi.Limiter(**kwargs)


limiter = get_limiter()


def get_admin_limit() -> str:
    return f"{app.config.settings.rate_limit_admin_per_minute}/minute"


def get_default_limit() -> str:
    return f"{app.config.settings.rate_limit_per_minute}/minute"


def get_suggest_limit() -> str:
    return f"{app.config.settings.rate_limit_suggest_per_minute}/minute"
