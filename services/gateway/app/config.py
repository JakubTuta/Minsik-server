import pydantic
import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    env: str = pydantic.Field(default="production")
    log_level: str = pydantic.Field(default="ERROR")

    gateway_host: str = pydantic.Field(default="0.0.0.0")
    gateway_http_port: int = pydantic.Field(default=8040)
    gateway_workers: int = pydantic.Field(default=2)

    ingestion_service_host: str = pydantic.Field(default="ingestion-service")
    ingestion_grpc_port: int = pydantic.Field(default=50054)

    books_service_host: str = pydantic.Field(default="books-service")
    books_grpc_port: int = pydantic.Field(default=50055)

    auth_service_host: str = pydantic.Field(default="auth-service")
    auth_grpc_port: int = pydantic.Field(default=50051)

    user_data_service_host: str = pydantic.Field(default="user-data-service")
    user_data_grpc_port: int = pydantic.Field(default=50053)

    recommendation_service_host: str = pydantic.Field(default="recommendation-service")
    recommendation_grpc_port: int = pydantic.Field(default=50056)

    redis_host: str = pydantic.Field(default="localhost")
    redis_port: int = pydantic.Field(default=6379)
    redis_password: str = pydantic.Field(default="")

    jwt_secret_key: str = pydantic.Field(default="changeme")
    jwt_algorithm: str = pydantic.Field(default="HS256")
    jwt_access_token_expire_minutes: int = pydantic.Field(default=15)
    refresh_token_expire_days: int = pydantic.Field(default=30)

    cookie_secure: bool = pydantic.Field(default=True)
    cookie_samesite: str = pydantic.Field(default="lax")
    cookie_domain: str = pydantic.Field(default="")

    grpc_keepalive_time_ms: int = pydantic.Field(default=300000)
    grpc_keepalive_timeout_ms: int = pydantic.Field(default=10000)
    grpc_timeout: float = pydantic.Field(default=10.0)
    grpc_recommendation_timeout: float = pydantic.Field(default=30.0)
    grpc_admin_timeout: float = pydantic.Field(default=60.0)
    recommendation_recompute_on_user_write: bool = pydantic.Field(default=True)

    cors_origins: str = pydantic.Field(default="http://localhost:3000")
    cors_allow_credentials: bool = pydantic.Field(default=True)
    cors_allow_methods: str = pydantic.Field(default="GET,POST,PUT,DELETE,PATCH,OPTIONS")
    cors_allow_headers: str = pydantic.Field(default="Content-Type,Authorization,X-CSRF-Token")

    rate_limit_enabled: bool = pydantic.Field(default=True)
    rate_limit_per_minute: int = pydantic.Field(default=60)
    rate_limit_admin_per_minute: int = pydantic.Field(default=20)
    rate_limit_suggest_per_minute: int = pydantic.Field(default=120)

    ledger_api_key: str = pydantic.Field(default="")

    trusted_proxy_ips: str = pydantic.Field(default="127.0.0.1")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @pydantic.model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.env == "production" and self.jwt_secret_key in ("", "changeme"):
            raise ValueError(
                "JWT_SECRET_KEY must be set to a strong secret in production"
            )
        return self

    @property
    def rate_limit_storage_uri(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/1"
        return f"redis://{self.redis_host}:{self.redis_port}/1"

    @property
    def ingestion_service_url(self) -> str:
        return f"{self.ingestion_service_host}:{self.ingestion_grpc_port}"

    @property
    def books_service_url(self) -> str:
        return f"{self.books_service_host}:{self.books_grpc_port}"

    @property
    def auth_service_url(self) -> str:
        return f"{self.auth_service_host}:{self.auth_grpc_port}"

    @property
    def user_data_service_url(self) -> str:
        return f"{self.user_data_service_host}:{self.user_data_grpc_port}"

    @property
    def recommendation_service_url(self) -> str:
        return f"{self.recommendation_service_host}:{self.recommendation_grpc_port}"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]


settings = Settings()
