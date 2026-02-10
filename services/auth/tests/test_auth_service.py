import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
import app.services.auth_service as auth_service
from tests.conftest import make_execute_result


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_success(self, mock_session):
        mock_session.execute.side_effect = [
            make_execute_result(None),
            make_execute_result(None),
        ]

        with patch('app.utils.hash_password', return_value='hashed_pw'):
            result = await auth_service.register(mock_session, "new@example.com", "newuser", "password")

        assert result.email == "new@example.com"
        assert result.username == "newuser"
        assert result.role == "user"
        assert result.is_active is True
        assert result.password_hash == "hashed_pw"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_email_taken(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        with pytest.raises(ValueError) as exc_info:
            await auth_service.register(mock_session, "test@example.com", "newuser", "password")

        assert str(exc_info.value) == "email_taken"

    @pytest.mark.asyncio
    async def test_register_username_taken(self, mock_session, mock_user):
        mock_session.execute.side_effect = [
            make_execute_result(None),
            make_execute_result(mock_user),
        ]

        with pytest.raises(ValueError) as exc_info:
            await auth_service.register(mock_session, "unique@example.com", "testuser", "password")

        assert str(exc_info.value) == "username_taken"

    @pytest.mark.asyncio
    async def test_register_hashes_password(self, mock_session):
        mock_session.execute.side_effect = [
            make_execute_result(None),
            make_execute_result(None),
        ]

        with patch('app.utils.hash_password', return_value='bcrypt_hashed') as mock_hash:
            result = await auth_service.register(mock_session, "a@b.com", "auser", "plaintext")

        mock_hash.assert_called_once_with("plaintext")
        assert result.password_hash == "bcrypt_hashed"


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        with patch('app.utils.verify_password', return_value=True):
            user, access_token, raw_refresh_token = await auth_service.login(
                mock_session, "test@example.com", "correct_password"
            )

        assert user is mock_user
        assert isinstance(access_token, str)
        assert len(access_token) > 0
        assert isinstance(raw_refresh_token, str)
        assert len(raw_refresh_token) > 0
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_user_not_found(self, mock_session):
        mock_session.execute.return_value = make_execute_result(None)

        with pytest.raises(ValueError) as exc_info:
            await auth_service.login(mock_session, "nobody@example.com", "password")

        assert str(exc_info.value) == "invalid_credentials"

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, mock_session, mock_user):
        mock_user.is_active = False
        mock_session.execute.return_value = make_execute_result(mock_user)

        with pytest.raises(ValueError) as exc_info:
            await auth_service.login(mock_session, "test@example.com", "password")

        assert str(exc_info.value) == "invalid_credentials"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        with patch('app.utils.verify_password', return_value=False):
            with pytest.raises(ValueError) as exc_info:
                await auth_service.login(mock_session, "test@example.com", "wrong_password")

        assert str(exc_info.value) == "invalid_credentials"
        assert mock_user.failed_login_attempts == 1

    @pytest.mark.asyncio
    async def test_login_increments_failed_attempts(self, mock_session, mock_user):
        mock_user.failed_login_attempts = 3
        mock_session.execute.return_value = make_execute_result(mock_user)

        with patch('app.utils.verify_password', return_value=False):
            with pytest.raises(ValueError):
                await auth_service.login(mock_session, "test@example.com", "wrong")

        assert mock_user.failed_login_attempts == 4

    @pytest.mark.asyncio
    async def test_login_locks_account_after_max_attempts(self, mock_session, mock_user):
        import app.config
        mock_user.failed_login_attempts = app.config.settings.max_failed_login_attempts - 1
        mock_session.execute.return_value = make_execute_result(mock_user)

        with patch('app.utils.verify_password', return_value=False):
            with pytest.raises(ValueError):
                await auth_service.login(mock_session, "test@example.com", "wrong")

        assert mock_user.locked_until is not None

    @pytest.mark.asyncio
    async def test_login_account_locked(self, mock_session, mock_user):
        mock_user.locked_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
        mock_session.execute.return_value = make_execute_result(mock_user)

        with pytest.raises(PermissionError) as exc_info:
            await auth_service.login(mock_session, "test@example.com", "password")

        assert str(exc_info.value) == "account_locked"

    @pytest.mark.asyncio
    async def test_login_resets_failed_attempts_on_success(self, mock_session, mock_user):
        mock_user.failed_login_attempts = 3
        mock_session.execute.return_value = make_execute_result(mock_user)

        with patch('app.utils.verify_password', return_value=True):
            await auth_service.login(mock_session, "test@example.com", "correct")

        assert mock_user.failed_login_attempts == 0


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_revokes_token(self, mock_session, mock_refresh_token):
        mock_session.execute.return_value = make_execute_result(mock_refresh_token)

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            await auth_service.logout(mock_session, "raw_token")

        assert mock_refresh_token.is_revoked is True
        assert mock_refresh_token.revoked_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_logout_token_not_found_is_silent(self, mock_session):
        mock_session.execute.return_value = make_execute_result(None)

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            await auth_service.logout(mock_session, "nonexistent_token")

        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_logout_already_revoked_token_is_silent(self, mock_session, mock_refresh_token):
        mock_refresh_token.is_revoked = True
        mock_session.execute.return_value = make_execute_result(mock_refresh_token)

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            await auth_service.logout(mock_session, "already_revoked_token")

        mock_session.commit.assert_not_called()


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_refresh_tokens_success(self, mock_session, mock_user, mock_refresh_token):
        mock_session.execute.side_effect = [
            make_execute_result(mock_refresh_token),
            make_execute_result(mock_user),
        ]

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            new_access_token, new_raw_refresh_token, user = await auth_service.refresh_tokens(
                mock_session, "raw_token"
            )

        assert isinstance(new_access_token, str)
        assert isinstance(new_raw_refresh_token, str)
        assert user is mock_user
        assert mock_refresh_token.is_revoked is True
        assert mock_refresh_token.revoked_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_tokens_not_found(self, mock_session):
        mock_session.execute.return_value = make_execute_result(None)

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            with pytest.raises(ValueError) as exc_info:
                await auth_service.refresh_tokens(mock_session, "unknown_token")

        assert str(exc_info.value) == "token_not_found"

    @pytest.mark.asyncio
    async def test_refresh_tokens_revoked(self, mock_session, mock_refresh_token):
        mock_refresh_token.is_revoked = True
        mock_session.execute.return_value = make_execute_result(mock_refresh_token)

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            with pytest.raises(PermissionError) as exc_info:
                await auth_service.refresh_tokens(mock_session, "revoked_token")

        assert str(exc_info.value) == "token_revoked"

    @pytest.mark.asyncio
    async def test_refresh_tokens_expired(self, mock_session, mock_refresh_token):
        mock_refresh_token.expires_at = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        mock_session.execute.return_value = make_execute_result(mock_refresh_token)

        with patch('app.services.token_service.hash_token', return_value='hashed'):
            with pytest.raises(PermissionError) as exc_info:
                await auth_service.refresh_tokens(mock_session, "expired_token")

        assert str(exc_info.value) == "token_expired"


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        result = await auth_service.get_current_user(mock_session, 1)

        assert result is mock_user

    @pytest.mark.asyncio
    async def test_get_current_user_not_found(self, mock_session):
        mock_session.execute.return_value = make_execute_result(None)

        with pytest.raises(ValueError) as exc_info:
            await auth_service.get_current_user(mock_session, 999)

        assert str(exc_info.value) == "user_not_found"


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_profile_display_name(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        result = await auth_service.update_profile(
            mock_session, 1, "New Name", None, None
        )

        assert mock_user.display_name == "New Name"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_profile_bio(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        await auth_service.update_profile(mock_session, 1, "", "New bio", None)

        assert mock_user.bio == "New bio"

    @pytest.mark.asyncio
    async def test_update_profile_avatar_url(self, mock_session, mock_user):
        mock_session.execute.return_value = make_execute_result(mock_user)

        await auth_service.update_profile(mock_session, 1, "", None, "https://example.com/avatar.jpg")

        assert mock_user.avatar_url == "https://example.com/avatar.jpg"

    @pytest.mark.asyncio
    async def test_update_profile_not_found(self, mock_session):
        mock_session.execute.return_value = make_execute_result(None)

        with pytest.raises(ValueError) as exc_info:
            await auth_service.update_profile(mock_session, 999, "Name", None, None)

        assert str(exc_info.value) == "user_not_found"


class TestIssueTokensForUser:
    @pytest.mark.asyncio
    async def test_issue_tokens_returns_tuple(self, mock_session, mock_user):
        result = await auth_service.issue_tokens_for_user(mock_session, mock_user)

        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_issue_tokens_access_token_is_string(self, mock_session, mock_user):
        access_token, _ = await auth_service.issue_tokens_for_user(mock_session, mock_user)

        assert isinstance(access_token, str)
        assert len(access_token) > 0

    @pytest.mark.asyncio
    async def test_issue_tokens_refresh_token_is_string(self, mock_session, mock_user):
        _, raw_refresh_token = await auth_service.issue_tokens_for_user(mock_session, mock_user)

        assert isinstance(raw_refresh_token, str)
        assert len(raw_refresh_token) > 0

    @pytest.mark.asyncio
    async def test_issue_tokens_saves_refresh_token(self, mock_session, mock_user):
        await auth_service.issue_tokens_for_user(mock_session, mock_user)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
