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
    db_pool_size: int = Field(default=3)
    db_max_overflow: int = Field(default=5)

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: str = Field(default="")
    redis_max_connections: int = Field(default=10)

    ingestion_service_host: str = Field(default="0.0.0.0")
    ingestion_grpc_port: int = Field(default=50054)

    open_library_api_url: str = Field(default="https://openlibrary.org")
    open_library_rate_limit: int = Field(default=50)

    google_books_api_url: str = Field(default="https://www.googleapis.com/books/v1")
    google_books_api_key: str = Field(default="")

    request_timeout: float = Field(default=30.0)

    ingestion_batch_size: int = Field(default=50)
    ingestion_max_retries: int = Field(default=3)
    ingestion_retry_delay: int = Field(default=5)

    continuous_fetch_enabled: bool = Field(default=True)
    continuous_ol_interval_hours: int = Field(default=1)
    continuous_ol_books_per_run: int = Field(default=100)
    continuous_gb_interval_hours: int = Field(default=6)
    continuous_gb_books_per_run: int = Field(default=40)

    description_enrich_enabled: bool = Field(default=True)
    description_enrich_interval_hours: int = Field(default=2)
    description_enrich_batch_size: int = Field(default=5)
    description_min_length: int = Field(default=100)

    ol_dump_base_url: str = Field(default="https://openlibrary.org/data")
    dump_batch_size: int = Field(default=500)
    dump_tmp_dir: str = Field(default="/tmp")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
