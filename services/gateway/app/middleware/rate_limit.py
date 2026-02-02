from slowapi import Limiter
from slowapi.util import get_remote_address
import app.config


def get_limiter() -> Limiter:
    return Limiter(
        key_func=get_remote_address,
        default_limits=[f"{app.config.settings.rate_limit_per_minute}/minute"],
        enabled=app.config.settings.rate_limit_enabled
    )


limiter = get_limiter()


def get_admin_limit() -> str:
    return f"{app.config.settings.rate_limit_admin_per_minute}/minute"


def get_default_limit() -> str:
    return f"{app.config.settings.rate_limit_per_minute}/minute"
