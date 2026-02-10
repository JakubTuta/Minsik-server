import typing
import logging
import datetime
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import select
import app.models.user
import app.models.refresh_token
import app.utils
import app.services.token_service
import app.config

logger = logging.getLogger(__name__)


async def register(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    email: str,
    username: str,
    password: str
) -> app.models.user.User:
    email_result = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.email == email)
    )
    if email_result.scalar_one_or_none():
        raise ValueError("email_taken")

    username_result = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.username == username)
    )
    if username_result.scalar_one_or_none():
        raise ValueError("username_taken")

    user = app.models.user.User(
        email=email,
        username=username,
        password_hash=app.utils.hash_password(password),
        role="user",
        is_active=True
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    email: str,
    password: str
) -> typing.Tuple[app.models.user.User, str, str]:
    result = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.email == email)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise ValueError("invalid_credentials")

    if user.locked_until and user.locked_until > datetime.datetime.utcnow():
        raise PermissionError("account_locked")

    if not app.utils.verify_password(password, user.password_hash):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= app.config.settings.max_failed_login_attempts:
            user.locked_until = datetime.datetime.utcnow() + datetime.timedelta(
                minutes=app.config.settings.lockout_duration_minutes
            )
        await session.commit()
        raise ValueError("invalid_credentials")

    access_token = app.services.token_service.create_access_token(user.user_id, user.role)
    raw_refresh_token, token_hash = app.services.token_service.create_refresh_token()

    refresh_token_obj = app.models.refresh_token.RefreshToken(
        user_id=user.user_id,
        token_hash=token_hash,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(
            days=app.config.settings.jwt_refresh_token_expire_days
        )
    )
    session.add(refresh_token_obj)

    user.last_login = datetime.datetime.utcnow()
    user.failed_login_attempts = 0
    user.locked_until = None
    await session.commit()

    return user, access_token, raw_refresh_token


async def logout(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    refresh_token_raw: str
) -> None:
    token_hash = app.services.token_service.hash_token(refresh_token_raw)
    result = await session.execute(
        select(app.models.refresh_token.RefreshToken).filter(
            app.models.refresh_token.RefreshToken.token_hash == token_hash
        )
    )
    token_obj = result.scalar_one_or_none()
    if token_obj and not token_obj.is_revoked:
        token_obj.is_revoked = True
        token_obj.revoked_at = datetime.datetime.utcnow()
        await session.commit()


async def refresh_tokens(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    refresh_token_raw: str
) -> typing.Tuple[str, str, app.models.user.User]:
    token_hash = app.services.token_service.hash_token(refresh_token_raw)
    result = await session.execute(
        select(app.models.refresh_token.RefreshToken).filter(
            app.models.refresh_token.RefreshToken.token_hash == token_hash
        )
    )
    token_obj = result.scalar_one_or_none()

    if not token_obj:
        raise ValueError("token_not_found")

    if token_obj.is_revoked:
        raise PermissionError("token_revoked")

    if token_obj.expires_at < datetime.datetime.utcnow():
        raise PermissionError("token_expired")

    user_result = await session.execute(
        select(app.models.user.User).filter(
            app.models.user.User.user_id == token_obj.user_id
        )
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError("user_not_found")

    new_access_token = app.services.token_service.create_access_token(user.user_id, user.role)
    new_raw_refresh_token, new_token_hash = app.services.token_service.create_refresh_token()

    new_refresh_token_obj = app.models.refresh_token.RefreshToken(
        user_id=user.user_id,
        token_hash=new_token_hash,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(
            days=app.config.settings.jwt_refresh_token_expire_days
        )
    )
    session.add(new_refresh_token_obj)
    await session.flush()

    token_obj.is_revoked = True
    token_obj.revoked_at = datetime.datetime.utcnow()
    token_obj.replaced_by_token_id = new_refresh_token_obj.token_id
    await session.commit()

    return new_access_token, new_raw_refresh_token, user


async def issue_tokens_for_user(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user: app.models.user.User
) -> typing.Tuple[str, str]:
    access_token = app.services.token_service.create_access_token(user.user_id, user.role)
    raw_refresh_token, token_hash = app.services.token_service.create_refresh_token()

    refresh_token_obj = app.models.refresh_token.RefreshToken(
        user_id=user.user_id,
        token_hash=token_hash,
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(
            days=app.config.settings.jwt_refresh_token_expire_days
        )
    )
    session.add(refresh_token_obj)
    await session.commit()

    return access_token, raw_refresh_token


async def get_current_user(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int
) -> app.models.user.User:
    result = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("user_not_found")
    return user


async def update_profile(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    user_id: int,
    display_name: str,
    bio: str,
    avatar_url: str
) -> app.models.user.User:
    result = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.user_id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("user_not_found")

    if display_name:
        user.display_name = display_name
    if bio is not None:
        user.bio = bio
    if avatar_url is not None:
        user.avatar_url = avatar_url

    await session.commit()
    await session.refresh(user)
    return user
