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

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: str = Field(default="")
    redis_max_connections: int = Field(default=20)

    books_service_host: str = Field(default="0.0.0.0")
    books_grpc_port: int = Field(default=50055)

    cache_book_detail_ttl: int = Field(default=3600)
    cache_author_detail_ttl: int = Field(default=3600)
    cache_author_books_ttl: int = Field(default=1800)
    cache_search_ttl: int = Field(default=900)
    cache_popular_ttl: int = Field(default=21600)

    view_count_flush_interval: int = Field(default=300)
    view_count_flush_batch_size: int = Field(default=100)

    search_default_limit: int = Field(default=10)
    search_max_limit: int = Field(default=100)
    search_author_books_expansion: int = Field(default=3)

    popularity_weight: float = Field(default=0.3)
    text_relevance_weight: float = Field(default=0.7)
    recent_views_days: int = Field(default=7)
    recent_views_multiplier: float = Field(default=2.0)

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
