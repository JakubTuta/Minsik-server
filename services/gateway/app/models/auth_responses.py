import typing
import pydantic
import app.models.responses


class UserSchema(pydantic.BaseModel):
    user_id: int
    email: str
    username: str
    display_name: typing.Optional[str] = None
    avatar_url: typing.Optional[str] = None
    bio: typing.Optional[str] = None
    role: str
    is_active: bool
    created_at: str


class AuthTokensData(pydantic.BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserSchema


class AuthResponse(pydantic.BaseModel):
    success: bool = True
    data: AuthTokensData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class UserData(pydantic.BaseModel):
    user: UserSchema


class UserResponse(pydantic.BaseModel):
    success: bool = True
    data: UserData
    error: typing.Optional[app.models.responses.ErrorDetail] = None


class RegisterRequest(pydantic.BaseModel):
    email: pydantic.EmailStr
    username: str = pydantic.Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = pydantic.Field(min_length=8, max_length=64)

    @pydantic.field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "username": "bookworm42",
                "password": "Secure123"
            }
        }
    )


class LoginRequest(pydantic.BaseModel):
    email: pydantic.EmailStr
    password: str = pydantic.Field(min_length=1)

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "securepassword123"
            }
        }
    )


class LogoutRequest(pydantic.BaseModel):
    refresh_token: str = pydantic.Field(min_length=1)

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    )


class RefreshTokenRequest(pydantic.BaseModel):
    refresh_token: str = pydantic.Field(min_length=1)

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    )


class UpdateProfileRequest(pydantic.BaseModel):
    display_name: typing.Optional[str] = pydantic.Field(default=None, max_length=100)
    bio: typing.Optional[str] = pydantic.Field(default=None, max_length=1000)
    avatar_url: typing.Optional[str] = pydantic.Field(default=None, max_length=500)

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "Book Lover",
                "bio": "I read everything I can get my hands on.",
                "avatar_url": "https://example.com/avatar.jpg"
            }
        }
    )
