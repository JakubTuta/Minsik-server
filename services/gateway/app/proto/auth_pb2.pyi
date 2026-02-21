from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RegisterRequest(_message.Message):
    __slots__ = ("email", "username", "password")
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    username: str
    password: str
    def __init__(self, email: _Optional[str] = ..., username: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class LoginRequest(_message.Message):
    __slots__ = ("email", "password")
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    def __init__(self, email: _Optional[str] = ..., password: _Optional[str] = ...) -> None: ...

class LogoutRequest(_message.Message):
    __slots__ = ("refresh_token",)
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    refresh_token: str
    def __init__(self, refresh_token: _Optional[str] = ...) -> None: ...

class RefreshTokenRequest(_message.Message):
    __slots__ = ("refresh_token",)
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    refresh_token: str
    def __init__(self, refresh_token: _Optional[str] = ...) -> None: ...

class ValidateTokenRequest(_message.Message):
    __slots__ = ("access_token",)
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    access_token: str
    def __init__(self, access_token: _Optional[str] = ...) -> None: ...

class ValidateTokenResponse(_message.Message):
    __slots__ = ("valid", "user_id", "role")
    VALID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    valid: bool
    user_id: int
    role: str
    def __init__(self, valid: bool = ..., user_id: _Optional[int] = ..., role: _Optional[str] = ...) -> None: ...

class GetCurrentUserRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class UpdateProfileRequest(_message.Message):
    __slots__ = ("user_id", "display_name", "bio", "avatar_url")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    BIO_FIELD_NUMBER: _ClassVar[int]
    AVATAR_URL_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    display_name: str
    bio: str
    avatar_url: str
    def __init__(self, user_id: _Optional[int] = ..., display_name: _Optional[str] = ..., bio: _Optional[str] = ..., avatar_url: _Optional[str] = ...) -> None: ...

class DeleteAccountRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    def __init__(self, user_id: _Optional[int] = ...) -> None: ...

class User(_message.Message):
    __slots__ = ("user_id", "email", "username", "display_name", "avatar_url", "bio", "role", "is_active", "created_at")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    AVATAR_URL_FIELD_NUMBER: _ClassVar[int]
    BIO_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    IS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    user_id: int
    email: str
    username: str
    display_name: str
    avatar_url: str
    bio: str
    role: str
    is_active: bool
    created_at: str
    def __init__(self, user_id: _Optional[int] = ..., email: _Optional[str] = ..., username: _Optional[str] = ..., display_name: _Optional[str] = ..., avatar_url: _Optional[str] = ..., bio: _Optional[str] = ..., role: _Optional[str] = ..., is_active: bool = ..., created_at: _Optional[str] = ...) -> None: ...

class AuthResponse(_message.Message):
    __slots__ = ("access_token", "refresh_token", "token_type", "user")
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    TOKEN_TYPE_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    access_token: str
    refresh_token: str
    token_type: str
    user: User
    def __init__(self, access_token: _Optional[str] = ..., refresh_token: _Optional[str] = ..., token_type: _Optional[str] = ..., user: _Optional[_Union[User, _Mapping]] = ...) -> None: ...

class UserResponse(_message.Message):
    __slots__ = ("user",)
    USER_FIELD_NUMBER: _ClassVar[int]
    user: User
    def __init__(self, user: _Optional[_Union[User, _Mapping]] = ...) -> None: ...

class EmptyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
