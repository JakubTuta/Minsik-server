import logging
import app.config
from app.grpc_clients import base
import app.proto.auth_pb2
import app.proto.auth_pb2_grpc

logger = logging.getLogger(__name__)


class AuthClient(base.GrpcClientBase):
    service_label = "auth"

    def _target(self) -> str:
        return app.config.settings.auth_service_url

    def _create_stub(self, channel):
        return app.proto.auth_pb2_grpc.AuthServiceStub(channel)


    async def register(
        self,
        email: str,
        username: str,
        password: str
    ) -> app.proto.auth_pb2.AuthResponse:
        request = app.proto.auth_pb2.RegisterRequest(
            email=email,
            username=username,
            password=password
        )

        return await self._call("Register", request)

    async def login(
        self,
        email: str,
        password: str
    ) -> app.proto.auth_pb2.AuthResponse:
        request = app.proto.auth_pb2.LoginRequest(
            email=email,
            password=password
        )

        return await self._call("Login", request)

    async def logout(self, refresh_token: str) -> app.proto.auth_pb2.EmptyResponse:
        request = app.proto.auth_pb2.LogoutRequest(refresh_token=refresh_token)

        return await self._call("Logout", request)

    async def refresh_token(self, refresh_token: str) -> app.proto.auth_pb2.AuthResponse:
        request = app.proto.auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)

        return await self._call("RefreshToken", request)

    async def get_current_user(self, user_id: int) -> app.proto.auth_pb2.UserResponse:
        request = app.proto.auth_pb2.GetCurrentUserRequest(user_id=user_id)

        return await self._call("GetCurrentUser", request)

    async def update_profile(
        self,
        user_id: int,
        display_name: str = "",
        bio: str = "",
        avatar_url: str = "",
        preferred_language: str = "",
    ) -> app.proto.auth_pb2.UserResponse:
        request = app.proto.auth_pb2.UpdateProfileRequest(
            user_id=user_id,
            display_name=display_name,
            bio=bio,
            avatar_url=avatar_url,
            preferred_language=preferred_language,
        )

        return await self._call("UpdateProfile", request)

    async def delete_account(self, user_id: int) -> app.proto.auth_pb2.EmptyResponse:
        request = app.proto.auth_pb2.DeleteAccountRequest(user_id=user_id)

        return await self._call("DeleteAccount", request)

    async def google_auth(self, code: str, redirect_uri: str) -> app.proto.auth_pb2.AuthResponse:
        request = app.proto.auth_pb2.GoogleAuthRequest(code=code, redirect_uri=redirect_uri)

        return await self._call("GoogleAuth", request)


auth_client = AuthClient()
