from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    env: str = Field(default="production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="ERROR")

    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="minsik_db")
    db_user: str = Field(default="postgres")
    db_password: str = Field(default="postgres")
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)

    auth_service_host: str = Field(default="0.0.0.0")
    auth_grpc_port: int = Field(default=50051)

    jwt_secret_key: str = Field(...)
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=15)
    jwt_refresh_token_expire_days: int = Field(default=30)

    bcrypt_rounds: int = Field(default=12)
    max_failed_login_attempts: int = Field(default=5)
    lockout_duration_minutes: int = Field(default=30)

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
