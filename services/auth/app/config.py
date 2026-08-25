import pydantic_settings
import pydantic


class Settings(pydantic_settings.BaseSettings):
    env: str = pydantic.Field(default="production")
    debug: bool = pydantic.Field(default=False)
    log_level: str = pydantic.Field(default="ERROR")

    db_host: str = pydantic.Field(default="localhost")
    db_port: int = pydantic.Field(default=5432)
    db_name: str = pydantic.Field(default="minsik_db")
    db_user: str = pydantic.Field(default="postgres")
    db_password: str = pydantic.Field(default="postgres")
    db_pool_size: int = pydantic.Field(default=5)
    db_max_overflow: int = pydantic.Field(default=5)

    auth_service_host: str = pydantic.Field(default="0.0.0.0")
    auth_grpc_port: int = pydantic.Field(default=50051)

    jwt_secret_key: str = pydantic.Field(...)
    jwt_algorithm: str = pydantic.Field(default="HS256")
    jwt_access_token_expire_minutes: int = pydantic.Field(default=15)
    jwt_refresh_token_expire_days: int = pydantic.Field(default=30)

    bcrypt_rounds: int = pydantic.Field(default=12)
    max_failed_login_attempts: int = pydantic.Field(default=5)
    lockout_duration_minutes: int = pydantic.Field(default=30)

    google_client_id: str = pydantic.Field(default="")
    google_client_secret: str = pydantic.Field(default="")
    google_token_url: str = pydantic.Field(default="https://oauth2.googleapis.com/token")
    google_userinfo_url: str = pydantic.Field(default="https://www.googleapis.com/oauth2/v3/userinfo")

    ledger_api_key: str = pydantic.Field(default="")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def listen_address(self) -> str:
        return f"{self.auth_service_host}:{self.auth_grpc_port}"


settings = Settings()
