import fastapi
import grpc
import logging
import typing
import app.config
import app.grpc_clients
import app.middleware.auth
import app.middleware.rate_limit
import app.models.auth_responses
import app.models.responses
import app.utils.responses

logger = logging.getLogger(__name__)

router = fastapi.APIRouter(prefix="/api/v1", tags=["Auth"])

limiter = app.middleware.rate_limit.limiter


def _user_proto_to_dict(user) -> typing.Dict[str, typing.Any]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name or None,
        "avatar_url": user.avatar_url or None,
        "bio": user.bio or None,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at
    }


def _auth_response_to_dict(response) -> typing.Dict[str, typing.Any]:
    return {
        "access_token": response.access_token,
        "refresh_token": response.refresh_token,
        "token_type": response.token_type,
        "user": _user_proto_to_dict(response.user)
    }


@router.post(
    "/auth/register",
    response_model=app.models.auth_responses.AuthResponse,
    summary="Register a new user",
    description="""
    Create a new user account. The account is immediately active — no email verification required.

    **Constraints:**
    - `email`: Valid email address, must be unique
    - `username`: 3–50 characters, alphanumeric plus `_` and `-`, must be unique
    - `password`: 8–64 characters, must contain at least one uppercase letter, one lowercase letter, and one digit

    Returns JWT access token, refresh token, and user profile on success.
    """,
    responses={
        201: {
            "description": "User registered successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                            "refresh_token": "550e8400-e29b-41d4-a716-446655440000",
                            "token_type": "Bearer",
                            "user": {
                                "user_id": 1,
                                "email": "user@example.com",
                                "username": "bookworm42",
                                "display_name": None,
                                "avatar_url": None,
                                "bio": None,
                                "role": "user",
                                "is_active": True,
                                "created_at": "2026-01-01T00:00:00"
                            }
                        },
                        "error": None
                    }
                }
            }
        },
        409: {
            "description": "Email or username already taken",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "ALREADY_EXISTS",
                            "message": "Email already registered",
                            "details": {}
                        }
                    }
                }
            }
        }
    }
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def register(
    request: fastapi.Request,
    body: app.models.auth_responses.RegisterRequest
):
    try:
        response = await app.grpc_clients.auth_client.register(
            email=body.email,
            username=body.username,
            password=body.password
        )
        return app.utils.responses.success_response(
            _auth_response_to_dict(response),
            status_code=201
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error during register: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.ALREADY_EXISTS:
            return app.utils.responses.error_response(
                code="ALREADY_EXISTS",
                message=e.details(),
                status_code=409
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            return app.utils.responses.error_response(
                code="INVALID_ARGUMENT",
                message=e.details(),
                status_code=400
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Registration failed",
            details={"grpc_code": e.code().name},
            status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error during register: {e}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500
        )


@router.post(
    "/auth/login",
    response_model=app.models.auth_responses.AuthResponse,
    summary="Log in",
    description="""
    Authenticate with email and password.

    Returns JWT access token (15-minute expiry), refresh token (30-day expiry), and user profile.

    Store the refresh token securely. Use `POST /api/v1/auth/refresh` to obtain a new access token
    when it expires.
    """,
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                            "refresh_token": "550e8400-e29b-41d4-a716-446655440000",
                            "token_type": "Bearer",
                            "user": {
                                "user_id": 1,
                                "email": "user@example.com",
                                "username": "bookworm42",
                                "display_name": "Book Lover",
                                "avatar_url": None,
                                "bio": None,
                                "role": "user",
                                "is_active": True,
                                "created_at": "2026-01-01T00:00:00"
                            }
                        },
                        "error": None
                    }
                }
            }
        },
        401: {
            "description": "Invalid credentials",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "UNAUTHENTICATED",
                            "message": "Invalid email or password",
                            "details": {}
                        }
                    }
                }
            }
        }
    }
)
@limiter.limit(app.middleware.rate_limit.get_admin_limit())
async def login(
    request: fastapi.Request,
    body: app.models.auth_responses.LoginRequest
):
    try:
        response = await app.grpc_clients.auth_client.login(
            email=body.email,
            password=body.password
        )
        return app.utils.responses.success_response(
            _auth_response_to_dict(response),
            status_code=200
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error during login: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            return app.utils.responses.error_response(
                code="UNAUTHENTICATED",
                message="Invalid email or password",
                status_code=401
            )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="UNAUTHENTICATED",
                message="Invalid email or password",
                status_code=401
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Login failed",
            details={"grpc_code": e.code().name},
            status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500
        )


@router.post(
    "/auth/logout",
    response_model=app.models.responses.APIResponse,
    summary="Log out",
    description="""
    Revoke the provided refresh token. The access token will expire naturally after 15 minutes.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {
            "description": "Logged out successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {"message": "Logged out successfully"},
                        "error": None
                    }
                }
            }
        },
        401: {"description": "Not authenticated"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def logout(
    request: fastapi.Request,
    body: app.models.auth_responses.LogoutRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        await app.grpc_clients.auth_client.logout(refresh_token=body.refresh_token)
        return app.utils.responses.success_response(
            {"message": "Logged out successfully"},
            status_code=200
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error during logout: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND",
                message="Token not found",
                status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Logout failed",
            details={"grpc_code": e.code().name},
            status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500
        )


@router.post(
    "/auth/refresh",
    response_model=app.models.auth_responses.AuthResponse,
    summary="Refresh access token",
    description="""
    Exchange a valid refresh token for a new access token and rotated refresh token.

    Refresh token rotation is enforced — each call invalidates the old refresh token
    and issues a new one. Store the new refresh token for the next refresh cycle.

    No `Authorization` header required; the refresh token in the request body is sufficient.
    """,
    responses={
        200: {
            "description": "Tokens refreshed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                            "refresh_token": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                            "token_type": "Bearer",
                            "user": {
                                "user_id": 1,
                                "email": "user@example.com",
                                "username": "bookworm42",
                                "display_name": "Book Lover",
                                "avatar_url": None,
                                "bio": None,
                                "role": "user",
                                "is_active": True,
                                "created_at": "2026-01-01T00:00:00"
                            }
                        },
                        "error": None
                    }
                }
            }
        },
        401: {
            "description": "Refresh token expired, revoked, or invalid",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "UNAUTHENTICATED",
                            "message": "Refresh token is invalid or expired",
                            "details": {}
                        }
                    }
                }
            }
        }
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def refresh_token(
    request: fastapi.Request,
    body: app.models.auth_responses.RefreshTokenRequest
):
    try:
        response = await app.grpc_clients.auth_client.refresh_token(
            refresh_token=body.refresh_token
        )
        return app.utils.responses.success_response(
            _auth_response_to_dict(response),
            status_code=200
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error during token refresh: {e.code()} - {e.details()}")
        if e.code() in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            return app.utils.responses.error_response(
                code="UNAUTHENTICATED",
                message="Refresh token is invalid or expired",
                status_code=401
            )
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="UNAUTHENTICATED",
                message="Refresh token is invalid or expired",
                status_code=401
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Token refresh failed",
            details={"grpc_code": e.code().name},
            status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error during token refresh: {e}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500
        )


@router.get(
    "/users/me",
    response_model=app.models.auth_responses.UserResponse,
    summary="Get current user profile",
    description="""
    Retrieve the full profile of the authenticated user.

    Requires a valid access token in the `Authorization: Bearer <token>` header.
    """,
    responses={
        200: {
            "description": "User profile retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "user": {
                                "user_id": 1,
                                "email": "user@example.com",
                                "username": "bookworm42",
                                "display_name": "Book Lover",
                                "avatar_url": "https://example.com/avatar.jpg",
                                "bio": "I read everything I can get my hands on.",
                                "role": "user",
                                "is_active": True,
                                "created_at": "2026-01-01T00:00:00"
                            }
                        },
                        "error": None
                    }
                }
            }
        },
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def get_current_user(
    request: fastapi.Request,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.auth_client.get_current_user(
            user_id=current_user["user_id"]
        )
        return app.utils.responses.success_response(
            {"user": _user_proto_to_dict(response.user)},
            status_code=200
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error getting current user: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND",
                message="User not found",
                status_code=404
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to retrieve user profile",
            details={"grpc_code": e.code().name},
            status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error getting current user: {e}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500
        )


@router.put(
    "/users/me",
    response_model=app.models.auth_responses.UserResponse,
    summary="Update current user profile",
    description="""
    Update the profile of the authenticated user.

    All fields are optional — only provided fields are updated.

    Requires a valid access token in the `Authorization: Bearer <token>` header.

    **Updatable fields:**
    - `display_name` — Public display name (max 100 characters)
    - `bio` — Short biography (max 1000 characters)
    - `avatar_url` — URL to profile picture (max 500 characters)
    """,
    responses={
        200: {
            "description": "Profile updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "user": {
                                "user_id": 1,
                                "email": "user@example.com",
                                "username": "bookworm42",
                                "display_name": "Updated Name",
                                "avatar_url": "https://example.com/new-avatar.jpg",
                                "bio": "Updated bio.",
                                "role": "user",
                                "is_active": True,
                                "created_at": "2026-01-01T00:00:00"
                            }
                        },
                        "error": None
                    }
                }
            }
        },
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"}
    }
)
@limiter.limit(app.middleware.rate_limit.get_default_limit())
async def update_profile(
    request: fastapi.Request,
    body: app.models.auth_responses.UpdateProfileRequest,
    current_user: typing.Dict[str, typing.Any] = fastapi.Depends(app.middleware.auth.require_user)
):
    try:
        response = await app.grpc_clients.auth_client.update_profile(
            user_id=current_user["user_id"],
            display_name=body.display_name or "",
            bio=body.bio or "",
            avatar_url=body.avatar_url or ""
        )
        return app.utils.responses.success_response(
            {"user": _user_proto_to_dict(response.user)},
            status_code=200
        )
    except grpc.RpcError as e:
        logger.error(f"gRPC error updating profile: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return app.utils.responses.error_response(
                code="NOT_FOUND",
                message="User not found",
                status_code=404
            )
        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
            return app.utils.responses.error_response(
                code="INVALID_ARGUMENT",
                message=e.details(),
                status_code=400
            )
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="Failed to update profile",
            details={"grpc_code": e.code().name},
            status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error updating profile: {e}")
        return app.utils.responses.error_response(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            status_code=500
        )
