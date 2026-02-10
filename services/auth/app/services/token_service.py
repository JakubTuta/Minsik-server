import uuid
import hashlib
import datetime
import typing
import jwt
import app.config


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(
            minutes=app.config.settings.jwt_access_token_expire_minutes
        ),
        "iat": datetime.datetime.utcnow(),
        "type": "access"
    }
    return jwt.encode(
        payload,
        app.config.settings.jwt_secret_key,
        algorithm=app.config.settings.jwt_algorithm
    )


def create_refresh_token() -> typing.Tuple[str, str]:
    raw_token = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def decode_access_token(token: str) -> typing.Dict[str, typing.Any]:
    return jwt.decode(
        token,
        app.config.settings.jwt_secret_key,
        algorithms=[app.config.settings.jwt_algorithm]
    )


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
