import datetime
import pytest
import grpc
import jwt
import fastapi
from fastapi.security import HTTPAuthorizationCredentials

import app.config
import app.grpc_clients
import app.middleware.auth


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details


def make_token(user_id: int = 1, role: str = "user") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    }
    return jwt.encode(
        payload,
        app.config.settings.jwt_secret_key,
        algorithm=app.config.settings.jwt_algorithm
    )


def make_expired_token(user_id: int = 1, role: str = "user") -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    }
    return jwt.encode(
        payload,
        app.config.settings.jwt_secret_key,
        algorithm=app.config.settings.jwt_algorithm
    )


def make_mock_user(mocker, user_id: int = 1, role: str = "user"):
    user = mocker.MagicMock()
    user.user_id = user_id
    user.email = "user@example.com"
    user.username = "bookworm42"
    user.display_name = "Book Lover"
    user.avatar_url = ""
    user.bio = ""
    user.role = role
    user.is_active = True
    user.created_at = "2026-01-01T00:00:00"
    return user


def make_mock_auth_response(mocker, user_id: int = 1, role: str = "user"):
    response = mocker.MagicMock()
    response.access_token = "test_access_token"
    response.refresh_token = "test_refresh_token"
    response.token_type = "Bearer"
    response.user = make_mock_user(mocker, user_id, role)
    return response


def make_mock_user_response(mocker, user_id: int = 1, role: str = "user"):
    response = mocker.MagicMock()
    response.user = make_mock_user(mocker, user_id, role)
    return response


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        result = await app.middleware.auth.get_current_user_optional(None)

        assert result is None

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_context(self):
        token = make_token(user_id=42, role="user")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        result = await app.middleware.auth.get_current_user_optional(creds)

        assert result is not None
        assert result["user_id"] == 42
        assert result["role"] == "user"

    @pytest.mark.asyncio
    async def test_admin_token_returns_admin_role(self):
        token = make_token(user_id=1, role="admin")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        result = await app.middleware.auth.get_current_user_optional(creds)

        assert result is not None
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_expired_token_returns_none(self):
        token = make_expired_token(user_id=1)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        result = await app.middleware.auth.get_current_user_optional(creds)

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_token_returns_none(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.valid.token")

        result = await app.middleware.auth.get_current_user_optional(creds)

        assert result is None

    @pytest.mark.asyncio
    async def test_require_user_raises_401_when_unauthenticated(self):
        with pytest.raises(fastapi.HTTPException) as exc_info:
            await app.middleware.auth.require_user(None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_user_returns_user_when_authenticated(self):
        user = {"user_id": 1, "role": "user"}

        result = await app.middleware.auth.require_user(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_require_admin_raises_403_for_user_role(self):
        user = {"user_id": 1, "role": "user"}

        with pytest.raises(fastapi.HTTPException) as exc_info:
            await app.middleware.auth.require_admin(user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_admin_passes_for_admin_role(self):
        user = {"user_id": 1, "role": "admin"}

        result = await app.middleware.auth.require_admin(user)

        assert result["role"] == "admin"


class TestRegisterEndpoint:
    def test_register_success(self, client, mock_auth_client, mocker):
        mock_auth_client.register.return_value = make_mock_auth_response(mocker)

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "bookworm42",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["error"] is None
        assert data["data"]["access_token"] == "test_access_token"
        assert data["data"]["refresh_token"] == "test_refresh_token"
        assert data["data"]["token_type"] == "Bearer"
        assert data["data"]["user"]["email"] == "user@example.com"
        assert data["data"]["user"]["username"] == "bookworm42"
        assert data["data"]["user"]["role"] == "user"

    def test_register_email_already_taken(self, client, mock_auth_client):
        mock_auth_client.register.side_effect = MockRpcError(
            grpc.StatusCode.ALREADY_EXISTS, "Email already registered"
        )

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "taken@example.com",
                "username": "newuser",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "ALREADY_EXISTS"
        assert data["error"]["message"] == "Email already registered"

    def test_register_invalid_argument_from_service(self, client, mock_auth_client):
        mock_auth_client.register.side_effect = MockRpcError(
            grpc.StatusCode.INVALID_ARGUMENT, "Username contains invalid characters"
        )

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "valid-user",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_ARGUMENT"

    def test_register_grpc_internal_error(self, client, mock_auth_client):
        mock_auth_client.register.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "Internal server error"
        )

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "bookworm42",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"

    def test_register_invalid_email_format(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "username": "bookworm42",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 422

    def test_register_password_too_short(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "bookworm42",
                "password": "short"
            }
        )

        assert response.status_code == 422

    def test_register_username_too_short(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "ab",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 422

    def test_register_username_invalid_characters(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "username": "user name with spaces",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 422


class TestLoginEndpoint:
    def test_login_success(self, client, mock_auth_client, mocker):
        mock_auth_client.login.return_value = make_mock_auth_response(mocker)

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "user@example.com",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["access_token"] == "test_access_token"
        assert data["data"]["user"]["username"] == "bookworm42"

    def test_login_wrong_password(self, client, mock_auth_client):
        mock_auth_client.login.side_effect = MockRpcError(
            grpc.StatusCode.UNAUTHENTICATED, "Invalid email or password"
        )

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "user@example.com",
                "password": "wrongpassword"
            }
        )

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UNAUTHENTICATED"

    def test_login_user_not_found_returns_401(self, client, mock_auth_client):
        mock_auth_client.login.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "User not found"
        )

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "somepassword123"
            }
        )

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UNAUTHENTICATED"

    def test_login_grpc_internal_error(self, client, mock_auth_client):
        mock_auth_client.login.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "Internal server error"
        )

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "user@example.com",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"

    def test_login_invalid_email_format(self, client):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "securepassword123"
            }
        )

        assert response.status_code == 422


class TestLogoutEndpoint:
    def test_logout_success(self, client, mock_auth_client):
        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "some-refresh-token"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["message"] == "Logged out successfully"

    def test_logout_requires_auth(self, client):
        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "some-refresh-token"}
        )

        assert response.status_code == 401

    def test_logout_expired_access_token_rejected(self, client):
        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "some-refresh-token"},
            headers={"Authorization": f"Bearer {make_expired_token()}"}
        )

        assert response.status_code == 401

    def test_logout_refresh_token_not_found(self, client, mock_auth_client):
        mock_auth_client.logout.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "Token not found"
        )

        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "nonexistent-token"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_logout_grpc_internal_error(self, client, mock_auth_client):
        mock_auth_client.logout.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "Internal server error"
        )

        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "some-refresh-token"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"


class TestRefreshTokenEndpoint:
    def test_refresh_token_success(self, client, mock_auth_client, mocker):
        mock_auth_client.refresh_token.return_value = make_mock_auth_response(mocker)

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "valid-refresh-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["access_token"] == "test_access_token"
        assert data["data"]["refresh_token"] == "test_refresh_token"

    def test_refresh_token_unauthenticated(self, client, mock_auth_client):
        mock_auth_client.refresh_token.side_effect = MockRpcError(
            grpc.StatusCode.UNAUTHENTICATED, "Refresh token is invalid or expired"
        )

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "expired-token"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UNAUTHENTICATED"

    def test_refresh_token_revoked(self, client, mock_auth_client):
        mock_auth_client.refresh_token.side_effect = MockRpcError(
            grpc.StatusCode.PERMISSION_DENIED, "Refresh token has been revoked"
        )

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "revoked-token"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UNAUTHENTICATED"

    def test_refresh_token_not_found(self, client, mock_auth_client):
        mock_auth_client.refresh_token.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "Token not found"
        )

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "unknown-token"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UNAUTHENTICATED"

    def test_refresh_token_grpc_internal_error(self, client, mock_auth_client):
        mock_auth_client.refresh_token.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "Internal server error"
        )

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "some-token"}
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"

    def test_refresh_token_empty_body(self, client):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": ""}
        )

        assert response.status_code == 422


class TestGetCurrentUserEndpoint:
    def test_get_current_user_success(self, client, mock_auth_client, mocker):
        mock_auth_client.get_current_user.return_value = make_mock_user_response(mocker)

        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {make_token(user_id=1)}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["user"]["user_id"] == 1
        assert data["data"]["user"]["email"] == "user@example.com"
        assert data["data"]["user"]["username"] == "bookworm42"
        assert data["data"]["user"]["role"] == "user"

    def test_get_current_user_requires_auth(self, client):
        response = client.get("/api/v1/users/me")

        assert response.status_code == 401

    def test_get_current_user_expired_token(self, client):
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {make_expired_token()}"}
        )

        assert response.status_code == 401

    def test_get_current_user_not_found(self, client, mock_auth_client):
        mock_auth_client.get_current_user.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "User not found"
        )

        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {make_token(user_id=999)}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_get_current_user_grpc_internal_error(self, client, mock_auth_client):
        mock_auth_client.get_current_user.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "Internal server error"
        )

        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"

    def test_get_current_user_passes_correct_user_id(self, client, mock_auth_client, mocker):
        mock_auth_client.get_current_user.return_value = make_mock_user_response(mocker, user_id=7)

        client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {make_token(user_id=7)}"}
        )

        mock_auth_client.get_current_user.assert_called_once_with(user_id=7)


class TestUpdateProfileEndpoint:
    def test_update_profile_success(self, client, mock_auth_client, mocker):
        updated_user = make_mock_user(mocker)
        updated_user.display_name = "New Name"
        updated_user.bio = "New bio"
        mock_response = mocker.MagicMock()
        mock_response.user = updated_user
        mock_auth_client.update_profile.return_value = mock_response

        response = client.put(
            "/api/v1/users/me",
            json={
                "display_name": "New Name",
                "bio": "New bio",
                "avatar_url": None
            },
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["user"]["display_name"] == "New Name"
        assert data["data"]["user"]["bio"] == "New bio"

    def test_update_profile_partial_update(self, client, mock_auth_client, mocker):
        mock_auth_client.update_profile.return_value = make_mock_user_response(mocker)

        response = client.put(
            "/api/v1/users/me",
            json={"display_name": "Only Name"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 200
        mock_auth_client.update_profile.assert_called_once_with(
            user_id=1,
            display_name="Only Name",
            bio="",
            avatar_url=""
        )

    def test_update_profile_requires_auth(self, client):
        response = client.put(
            "/api/v1/users/me",
            json={"display_name": "New Name"}
        )

        assert response.status_code == 401

    def test_update_profile_not_found(self, client, mock_auth_client):
        mock_auth_client.update_profile.side_effect = MockRpcError(
            grpc.StatusCode.NOT_FOUND, "User not found"
        )

        response = client.put(
            "/api/v1/users/me",
            json={"display_name": "New Name"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "NOT_FOUND"

    def test_update_profile_invalid_argument(self, client, mock_auth_client):
        mock_auth_client.update_profile.side_effect = MockRpcError(
            grpc.StatusCode.INVALID_ARGUMENT, "Avatar URL format is invalid"
        )

        response = client.put(
            "/api/v1/users/me",
            json={"avatar_url": "not-a-valid-url"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_ARGUMENT"

    def test_update_profile_grpc_internal_error(self, client, mock_auth_client):
        mock_auth_client.update_profile.side_effect = MockRpcError(
            grpc.StatusCode.INTERNAL, "Internal server error"
        )

        response = client.put(
            "/api/v1/users/me",
            json={"display_name": "New Name"},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"

    def test_update_profile_display_name_too_long(self, client):
        response = client.put(
            "/api/v1/users/me",
            json={"display_name": "A" * 101},
            headers={"Authorization": f"Bearer {make_token()}"}
        )

        assert response.status_code == 422
