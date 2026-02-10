import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.user_id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.display_name = "Test User"
    user.password_hash = "$2b$12$fakehash"
    user.role = "user"
    user.is_active = True
    user.avatar_url = None
    user.bio = None
    user.last_login = None
    user.failed_login_attempts = 0
    user.locked_until = None
    user.created_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    user.updated_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    return user


@pytest.fixture
def mock_refresh_token():
    token = MagicMock()
    token.token_id = 1
    token.user_id = 1
    token.token_hash = "abc123def456" * 5 + "abcd"
    token.is_revoked = False
    token.expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
    token.revoked_at = None
    token.replaced_by_token_id = None
    return token


def make_execute_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    return result
