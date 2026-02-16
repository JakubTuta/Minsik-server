import re
import grpc
import logging
import jwt
import app.proto.auth_pb2
import app.proto.auth_pb2_grpc
import app.database
import app.services.auth_service
import app.services.token_service

logger = logging.getLogger(__name__)

_EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _validate_register_input(email: str, password: str) -> None:
    if not _EMAIL_REGEX.match(email):
        raise ValueError("invalid_email")
    if not (8 <= len(password) <= 64):
        raise ValueError("invalid_password")
    if not any(c.isupper() for c in password):
        raise ValueError("invalid_password")
    if not any(c.islower() for c in password):
        raise ValueError("invalid_password")
    if not any(c.isdigit() for c in password):
        raise ValueError("invalid_password")


def _build_user_message(user: object) -> app.proto.auth_pb2.User:
    return app.proto.auth_pb2.User(
        user_id=user.user_id,
        email=user.email,
        username=user.username,
        display_name=user.display_name or "",
        avatar_url=user.avatar_url or "",
        bio=user.bio or "",
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else ""
    )


class AuthServicer(app.proto.auth_pb2_grpc.AuthServiceServicer):
    async def Register(
        self,
        request: app.proto.auth_pb2.RegisterRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.AuthResponse:
        try:
            _validate_register_input(request.email, request.password)
            async with app.database.async_session_maker() as session:
                user = await app.services.auth_service.register(
                    session,
                    request.email,
                    request.username,
                    request.password
                )
                access_token, raw_refresh_token = await app.services.auth_service.issue_tokens_for_user(
                    session, user
                )
                return app.proto.auth_pb2.AuthResponse(
                    access_token=access_token,
                    refresh_token=raw_refresh_token,
                    token_type="Bearer",
                    user=_build_user_message(user)
                )
        except ValueError as e:
            error_key = str(e)
            if error_key in ("email_taken", "username_taken"):
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, f"Registration failed: {error_key}")
            else:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Invalid input: {error_key}")
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in Register: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Registration failed: {str(e)}")

    async def Login(
        self,
        request: app.proto.auth_pb2.LoginRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.AuthResponse:
        try:
            async with app.database.async_session_maker() as session:
                user, access_token, raw_refresh_token = await app.services.auth_service.login(
                    session,
                    request.email,
                    request.password
                )
                return app.proto.auth_pb2.AuthResponse(
                    access_token=access_token,
                    refresh_token=raw_refresh_token,
                    token_type="Bearer",
                    user=_build_user_message(user)
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, f"Login failed: {str(e)}")
        except PermissionError as e:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, f"Login failed: {str(e)}")
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in Login: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Login failed: {str(e)}")

    async def Logout(
        self,
        request: app.proto.auth_pb2.LogoutRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                await app.services.auth_service.logout(session, request.refresh_token)
                return app.proto.auth_pb2.EmptyResponse()
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in Logout: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Logout failed: {str(e)}")

    async def RefreshToken(
        self,
        request: app.proto.auth_pb2.RefreshTokenRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.AuthResponse:
        try:
            async with app.database.async_session_maker() as session:
                new_access_token, new_raw_refresh_token, user = await app.services.auth_service.refresh_tokens(
                    session,
                    request.refresh_token
                )
                return app.proto.auth_pb2.AuthResponse(
                    access_token=new_access_token,
                    refresh_token=new_raw_refresh_token,
                    token_type="Bearer",
                    user=_build_user_message(user)
                )
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Token not found: {str(e)}")
        except PermissionError as e:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, f"Token invalid: {str(e)}")
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in RefreshToken: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Token refresh failed: {str(e)}")

    async def ValidateToken(
        self,
        request: app.proto.auth_pb2.ValidateTokenRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.ValidateTokenResponse:
        try:
            payload = app.services.token_service.decode_access_token(request.access_token)
            return app.proto.auth_pb2.ValidateTokenResponse(
                valid=True,
                user_id=int(payload["sub"]),
                role=payload["role"]
            )
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return app.proto.auth_pb2.ValidateTokenResponse(valid=False, user_id=0, role="")
        except Exception as e:
            logger.error(f"Error in ValidateToken: {str(e)}")
            return app.proto.auth_pb2.ValidateTokenResponse(valid=False, user_id=0, role="")

    async def GetCurrentUser(
        self,
        request: app.proto.auth_pb2.GetCurrentUserRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.UserResponse:
        try:
            async with app.database.async_session_maker() as session:
                user = await app.services.auth_service.get_current_user(session, request.user_id)
                return app.proto.auth_pb2.UserResponse(user=_build_user_message(user))
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"User not found: {str(e)}")
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in GetCurrentUser: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Get user failed: {str(e)}")

    async def UpdateProfile(
        self,
        request: app.proto.auth_pb2.UpdateProfileRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.UserResponse:
        try:
            async with app.database.async_session_maker() as session:
                user = await app.services.auth_service.update_profile(
                    session,
                    request.user_id,
                    request.display_name,
                    request.bio,
                    request.avatar_url
                )
                return app.proto.auth_pb2.UserResponse(user=_build_user_message(user))
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"User not found: {str(e)}")
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in UpdateProfile: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Update profile failed: {str(e)}")

    async def DeleteAccount(
        self,
        request: app.proto.auth_pb2.DeleteAccountRequest,
        context: grpc.aio.ServicerContext
    ) -> app.proto.auth_pb2.EmptyResponse:
        try:
            async with app.database.async_session_maker() as session:
                await app.services.auth_service.delete_account(session, request.user_id)
                return app.proto.auth_pb2.EmptyResponse()
        except ValueError as e:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"User not found: {str(e)}")
        except grpc.aio.AbortError:
            raise
        except Exception as e:
            logger.error(f"Error in DeleteAccount: {str(e)}")
            await context.abort(grpc.StatusCode.INTERNAL, f"Delete account failed: {str(e)}")
