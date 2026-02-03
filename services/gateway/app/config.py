from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    env: str = Field(default="production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="ERROR")

    gateway_host: str = Field(default="0.0.0.0")
    gateway_http_port: int = Field(default=8040)
    gateway_workers: int = Field(default=2)

    ingestion_service_host: str = Field(default="ingestion-service")
    ingestion_grpc_port: int = Field(default=50054)

    books_service_host: str = Field(default="books-service")
    books_grpc_port: int = Field(default=50055)

    grpc_pool_size: int = Field(default=1)
    grpc_keepalive_time_ms: int = Field(default=60000)
    grpc_keepalive_timeout_ms: int = Field(default=10000)
    grpc_timeout: float = Field(default=10.0)

    cors_origins: str = Field(default="*")
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: str = Field(default="*")
    cors_allow_headers: str = Field(default="*")

    rate_limit_enabled: bool = Field(default=False)
    rate_limit_per_minute: int = Field(default=60)
    rate_limit_burst: int = Field(default=10)
    rate_limit_admin_per_minute: int = Field(default=20)

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def ingestion_service_url(self) -> str:
        return f"{self.ingestion_service_host}:{self.ingestion_grpc_port}"

    @property
    def books_service_url(self) -> str:
        return f"{self.books_service_host}:{self.books_grpc_port}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
