import typing
import logging
import jwt
import fastapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import app.config

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def _decode_access_token(token: str) -> typing.Optional[typing.Dict[str, typing.Any]]:
    try:
        payload = jwt.decode(
            token,
            app.config.settings.jwt_secret_key,
            algorithms=[app.config.settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Access token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Invalid access token: {e}")
        return None


async def get_current_user_optional(
    credentials: typing.Optional[HTTPAuthorizationCredentials] = fastapi.Depends(_bearer_scheme)
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    if not credentials:
        return None

    payload = _decode_access_token(credentials.credentials)
    if not payload:
        return None

    user_id = payload.get("sub")
    role = payload.get("role")

    if not user_id or not role:
        return None

    return {"user_id": int(user_id), "role": role}


async def require_user(
    user: typing.Optional[typing.Dict[str, typing.Any]] = fastapi.Depends(get_current_user_optional)
) -> typing.Dict[str, typing.Any]:
    if user is None:
        raise fastapi.HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


async def require_admin(
    user: typing.Dict[str, typing.Any] = fastapi.Depends(require_user)
) -> typing.Dict[str, typing.Any]:
    if user.get("role") != "admin":
        raise fastapi.HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    return user
