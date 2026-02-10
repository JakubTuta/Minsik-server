import grpc
import logging
import typing
import app.config
import app.proto.auth_pb2 as auth_pb2
import app.proto.auth_pb2_grpc as auth_pb2_grpc

logger = logging.getLogger(__name__)


class AuthClient:
    def __init__(self):
        self.channel: typing.Optional[grpc.aio.Channel] = None
        self.stub: typing.Optional[auth_pb2_grpc.AuthServiceStub] = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        self.channel = grpc.aio.insecure_channel(
            app.config.settings.auth_service_url,
            options=[
                ("grpc.keepalive_time_ms", app.config.settings.grpc_keepalive_time_ms),
                ("grpc.keepalive_timeout_ms", app.config.settings.grpc_keepalive_timeout_ms),
                ("grpc.keepalive_permit_without_calls", 1),
                ("grpc.http2.max_pings_without_data", 0),
            ]
        )
        self.stub = auth_pb2_grpc.AuthServiceStub(self.channel)
        logger.info(f"Connected to auth service at {app.config.settings.auth_service_url}")

    async def close(self):
        if self.channel:
            await self.channel.close()
            logger.info("Closed auth service connection")

    async def register(
        self,
        email: str,
        username: str,
        password: str
    ) -> auth_pb2.AuthResponse:
        request = auth_pb2.RegisterRequest(
            email=email,
            username=username,
            password=password
        )

        try:
            response = await self.stub.Register(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error registering user: {e.code()} - {e.details()}")
            raise

    async def login(
        self,
        email: str,
        password: str
    ) -> auth_pb2.AuthResponse:
        request = auth_pb2.LoginRequest(
            email=email,
            password=password
        )

        try:
            response = await self.stub.Login(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error logging in: {e.code()} - {e.details()}")
            raise

    async def logout(self, refresh_token: str) -> auth_pb2.EmptyResponse:
        request = auth_pb2.LogoutRequest(refresh_token=refresh_token)

        try:
            response = await self.stub.Logout(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error logging out: {e.code()} - {e.details()}")
            raise

    async def refresh_token(self, refresh_token: str) -> auth_pb2.AuthResponse:
        request = auth_pb2.RefreshTokenRequest(refresh_token=refresh_token)

        try:
            response = await self.stub.RefreshToken(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error refreshing token: {e.code()} - {e.details()}")
            raise

    async def get_current_user(self, user_id: int) -> auth_pb2.UserResponse:
        request = auth_pb2.GetCurrentUserRequest(user_id=user_id)

        try:
            response = await self.stub.GetCurrentUser(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error getting current user: {e.code()} - {e.details()}")
            raise

    async def update_profile(
        self,
        user_id: int,
        display_name: str = "",
        bio: str = "",
        avatar_url: str = ""
    ) -> auth_pb2.UserResponse:
        request = auth_pb2.UpdateProfileRequest(
            user_id=user_id,
            display_name=display_name,
            bio=bio,
            avatar_url=avatar_url
        )

        try:
            response = await self.stub.UpdateProfile(
                request,
                timeout=app.config.settings.grpc_timeout
            )
            return response
        except grpc.RpcError as e:
            logger.error(f"gRPC error updating profile: {e.code()} - {e.details()}")
            raise


auth_client = AuthClient()
