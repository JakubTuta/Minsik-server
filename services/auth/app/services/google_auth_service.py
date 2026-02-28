import re
import typing
import logging
import datetime
import httpx
import sqlalchemy
import sqlalchemy.ext.asyncio
from sqlalchemy import select
import app.models.user
import app.config

logger = logging.getLogger(__name__)

_SLUG_SANITIZE_RE = re.compile(r'[^a-z0-9_]')
_MULTI_UNDERSCORE_RE = re.compile(r'_+')


async def exchange_code_for_tokens(
    code: str,
    redirect_uri: str
) -> typing.Dict[str, typing.Any]:
    if not app.config.settings.google_client_id:
        raise ValueError("google_oauth_not_configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                app.config.settings.google_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": app.config.settings.google_client_id,
                    "client_secret": app.config.settings.google_client_secret,
                }
            )
        if response.status_code != 200:
            logger.warning(f"Google token exchange failed with status {response.status_code}: {response.text}")
            raise ValueError("google_token_exchange_failed")
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during Google token exchange: {e}")
        raise ValueError("google_token_exchange_failed")


async def fetch_google_user_info(
    access_token: str
) -> typing.Dict[str, typing.Any]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                app.config.settings.google_userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code != 200:
            logger.warning(f"Google userinfo failed with status {response.status_code}: {response.text}")
            raise ValueError("google_userinfo_failed")
        return response.json()
    except httpx.HTTPError as e:
        logger.error(f"HTTP error during Google userinfo fetch: {e}")
        raise ValueError("google_userinfo_failed")


def _build_username_candidate(display_name: str, email: str) -> str:
    base = display_name.strip() if display_name.strip() else email.split("@")[0]
    base = _SLUG_SANITIZE_RE.sub("_", base.lower())
    base = _MULTI_UNDERSCORE_RE.sub("_", base).strip("_")
    base = base[:40]
    return base if base else "user"


async def _generate_unique_username(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    display_name: str,
    email: str
) -> str:
    candidate = _build_username_candidate(display_name, email)
    result = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.username == candidate)
    )
    if not result.scalar_one_or_none():
        return candidate

    counter = 2
    while True:
        suffixed = f"{candidate}_{counter}"
        result = await session.execute(
            select(app.models.user.User).filter(app.models.user.User.username == suffixed)
        )
        if not result.scalar_one_or_none():
            return suffixed
        counter += 1


async def authenticate_with_google(
    session: sqlalchemy.ext.asyncio.AsyncSession,
    code: str,
    redirect_uri: str
) -> app.models.user.User:
    token_data = await exchange_code_for_tokens(code, redirect_uri)

    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("google_token_missing")

    user_info = await fetch_google_user_info(access_token)

    google_id = user_info.get("sub")
    email = user_info.get("email")
    display_name = user_info.get("name", "")
    avatar_url = user_info.get("picture")

    if not email:
        raise ValueError("google_email_missing")

    existing_by_google_id = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.google_id == google_id)
    )
    user = existing_by_google_id.scalar_one_or_none()
    if user:
        if not user.is_active:
            raise PermissionError("account_inactive")
        user.last_login = datetime.datetime.utcnow()
        await session.commit()
        return user

    existing_by_email = await session.execute(
        select(app.models.user.User).filter(app.models.user.User.email == email)
    )
    user = existing_by_email.scalar_one_or_none()
    if user:
        if not user.is_active:
            raise PermissionError("account_inactive")
        user.google_id = google_id
        if not user.avatar_url and avatar_url:
            user.avatar_url = avatar_url
        user.last_login = datetime.datetime.utcnow()
        await session.commit()
        await session.refresh(user)
        return user

    username = await _generate_unique_username(session, display_name, email)
    new_user = app.models.user.User(
        email=email,
        username=username,
        display_name=display_name or None,
        google_id=google_id,
        avatar_url=avatar_url,
        password_hash=None,
        role="user",
        is_active=True,
        last_login=datetime.datetime.utcnow(),
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user
