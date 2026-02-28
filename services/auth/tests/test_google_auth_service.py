import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import app.services.google_auth_service as google_auth_service


def make_mock_user(google_id="123456", email="google@example.com", avatar_url=None):
    user = MagicMock()
    user.user_id = 1
    user.email = email
    user.username = "google_user"
    user.display_name = "Google User"
    user.google_id = google_id
    user.password_hash = None
    user.avatar_url = avatar_url
    user.is_active = True
    user.last_login = None
    return user


def make_execute_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestBuildUsernameCandidate:
    def test_uses_display_name_when_provided(self):
        result = google_auth_service._build_username_candidate("John Doe", "john@example.com")
        assert result == "john_doe"

    def test_falls_back_to_email_local_part(self):
        result = google_auth_service._build_username_candidate("", "bookworm@example.com")
        assert result == "bookworm"

    def test_lowercases_result(self):
        result = google_auth_service._build_username_candidate("ALICE", "alice@example.com")
        assert result == "alice"

    def test_replaces_spaces_with_underscores(self):
        result = google_auth_service._build_username_candidate("Mary Jane Watson", "m@example.com")
        assert result == "mary_jane_watson"

    def test_strips_special_characters(self):
        result = google_auth_service._build_username_candidate("O'Brien!", "o@example.com")
        assert "'" not in result
        assert "!" not in result

    def test_collapses_consecutive_underscores(self):
        result = google_auth_service._build_username_candidate("Hello  World", "h@example.com")
        assert "__" not in result

    def test_truncates_to_40_characters(self):
        long_name = "a" * 60
        result = google_auth_service._build_username_candidate(long_name, "a@example.com")
        assert len(result) <= 40

    def test_falls_back_to_user_when_empty_after_sanitization(self):
        result = google_auth_service._build_username_candidate("!!!", "@example.com")
        assert result == "user"


class TestGenerateUniqueUsername:
    @pytest.mark.asyncio
    async def test_returns_candidate_when_no_conflict(self, mock_session):
        mock_session.execute.return_value = make_execute_result(None)
        result = await google_auth_service._generate_unique_username(
            mock_session, "John Doe", "john@example.com"
        )
        assert result == "john_doe"

    @pytest.mark.asyncio
    async def test_appends_suffix_on_collision(self, mock_session):
        existing_user = make_mock_user()
        mock_session.execute.side_effect = [
            make_execute_result(existing_user),
            make_execute_result(None),
        ]
        result = await google_auth_service._generate_unique_username(
            mock_session, "John Doe", "john@example.com"
        )
        assert result == "john_doe_2"

    @pytest.mark.asyncio
    async def test_increments_suffix_until_free(self, mock_session):
        existing_user = make_mock_user()
        mock_session.execute.side_effect = [
            make_execute_result(existing_user),
            make_execute_result(existing_user),
            make_execute_result(existing_user),
            make_execute_result(None),
        ]
        result = await google_auth_service._generate_unique_username(
            mock_session, "John Doe", "john@example.com"
        )
        assert result == "john_doe_4"


class TestExchangeCodeForTokens:
    @pytest.mark.asyncio
    async def test_raises_when_not_configured(self):
        with patch.object(app.services.google_auth_service.app.config.settings, "google_client_id", ""):
            with pytest.raises(ValueError, match="google_oauth_not_configured"):
                await google_auth_service.exchange_code_for_tokens("code", "http://localhost/cb")

    @pytest.mark.asyncio
    async def test_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "goog_access", "token_type": "Bearer"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__.return_value = mock_client
            with patch.object(app.services.google_auth_service.app.config.settings, "google_client_id", "fake-id"):
                result = await google_auth_service.exchange_code_for_tokens("code", "http://localhost/cb")

        assert result["access_token"] == "goog_access"

    @pytest.mark.asyncio
    async def test_raises_on_non_200_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__.return_value = mock_client
            with patch.object(app.services.google_auth_service.app.config.settings, "google_client_id", "fake-id"):
                with pytest.raises(ValueError, match="google_token_exchange_failed"):
                    await google_auth_service.exchange_code_for_tokens("bad_code", "http://localhost/cb")

    @pytest.mark.asyncio
    async def test_raises_on_httpx_error(self):
        import httpx
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__.return_value = mock_client
            with patch.object(app.services.google_auth_service.app.config.settings, "google_client_id", "fake-id"):
                with pytest.raises(ValueError, match="google_token_exchange_failed"):
                    await google_auth_service.exchange_code_for_tokens("code", "http://localhost/cb")


class TestFetchGoogleUserInfo:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "123456",
            "email": "google@example.com",
            "name": "Google User",
            "picture": "https://example.com/photo.jpg"
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__.return_value = mock_client
            result = await google_auth_service.fetch_google_user_info("goog_access")

        assert result["sub"] == "123456"
        assert result["email"] == "google@example.com"

    @pytest.mark.asyncio
    async def test_raises_on_non_200_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__.return_value = mock_client
            with pytest.raises(ValueError, match="google_userinfo_failed"):
                await google_auth_service.fetch_google_user_info("bad_token")

    @pytest.mark.asyncio
    async def test_raises_on_httpx_error(self):
        import httpx
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient") as mock_class:
            mock_class.return_value.__aenter__.return_value = mock_client
            with pytest.raises(ValueError, match="google_userinfo_failed"):
                await google_auth_service.fetch_google_user_info("goog_access")


class TestAuthenticateWithGoogle:
    _token_data = {"access_token": "goog_access"}
    _user_info = {
        "sub": "123456",
        "email": "google@example.com",
        "name": "Google User",
        "picture": "https://example.com/photo.jpg"
    }

    @pytest.mark.asyncio
    async def test_returns_existing_user_by_google_id(self, mock_session):
        existing_user = make_mock_user(google_id="123456")
        mock_session.execute.return_value = make_execute_result(existing_user)

        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value=self._token_data)):
            with patch.object(google_auth_service, "fetch_google_user_info", AsyncMock(return_value=self._user_info)):
                result = await google_auth_service.authenticate_with_google(
                    mock_session, "code", "http://localhost/cb"
                )

        assert result is existing_user

    @pytest.mark.asyncio
    async def test_links_google_to_existing_email_user(self, mock_session):
        password_user = make_mock_user(google_id=None, email="google@example.com")
        password_user.google_id = None
        mock_session.execute.side_effect = [
            make_execute_result(None),
            make_execute_result(password_user),
        ]

        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value=self._token_data)):
            with patch.object(google_auth_service, "fetch_google_user_info", AsyncMock(return_value=self._user_info)):
                result = await google_auth_service.authenticate_with_google(
                    mock_session, "code", "http://localhost/cb"
                )

        assert result is password_user
        assert result.google_id == "123456"

    @pytest.mark.asyncio
    async def test_creates_new_user_when_no_match(self, mock_session):
        mock_session.execute.side_effect = [
            make_execute_result(None),
            make_execute_result(None),
            make_execute_result(None),
        ]

        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value=self._token_data)):
            with patch.object(google_auth_service, "fetch_google_user_info", AsyncMock(return_value=self._user_info)):
                result = await google_auth_service.authenticate_with_google(
                    mock_session, "code", "http://localhost/cb"
                )

        mock_session.add.assert_called_once()
        added_user = mock_session.add.call_args[0][0]
        assert added_user.email == "google@example.com"
        assert added_user.google_id == "123456"
        assert added_user.password_hash is None

    @pytest.mark.asyncio
    async def test_raises_when_code_exchange_fails(self, mock_session):
        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(side_effect=ValueError("google_token_exchange_failed"))):
            with pytest.raises(ValueError, match="google_token_exchange_failed"):
                await google_auth_service.authenticate_with_google(
                    mock_session, "bad_code", "http://localhost/cb"
                )

    @pytest.mark.asyncio
    async def test_raises_when_access_token_missing(self, mock_session):
        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value={})):
            with pytest.raises(ValueError, match="google_token_missing"):
                await google_auth_service.authenticate_with_google(
                    mock_session, "code", "http://localhost/cb"
                )

    @pytest.mark.asyncio
    async def test_raises_when_email_missing(self, mock_session):
        user_info_no_email = {"sub": "123456", "name": "No Email"}
        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value=self._token_data)):
            with patch.object(google_auth_service, "fetch_google_user_info", AsyncMock(return_value=user_info_no_email)):
                with pytest.raises(ValueError, match="google_email_missing"):
                    await google_auth_service.authenticate_with_google(
                        mock_session, "code", "http://localhost/cb"
                    )

    @pytest.mark.asyncio
    async def test_raises_permission_error_for_inactive_user(self, mock_session):
        inactive_user = make_mock_user(google_id="123456")
        inactive_user.is_active = False
        mock_session.execute.return_value = make_execute_result(inactive_user)

        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value=self._token_data)):
            with patch.object(google_auth_service, "fetch_google_user_info", AsyncMock(return_value=self._user_info)):
                with pytest.raises(PermissionError, match="account_inactive"):
                    await google_auth_service.authenticate_with_google(
                        mock_session, "code", "http://localhost/cb"
                    )

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_avatar_on_link(self, mock_session):
        password_user = make_mock_user(google_id=None, email="google@example.com", avatar_url="https://existing.com/avatar.jpg")
        password_user.google_id = None
        mock_session.execute.side_effect = [
            make_execute_result(None),
            make_execute_result(password_user),
        ]

        with patch.object(google_auth_service, "exchange_code_for_tokens", AsyncMock(return_value=self._token_data)):
            with patch.object(google_auth_service, "fetch_google_user_info", AsyncMock(return_value=self._user_info)):
                result = await google_auth_service.authenticate_with_google(
                    mock_session, "code", "http://localhost/cb"
                )

        assert result.avatar_url == "https://existing.com/avatar.jpg"
