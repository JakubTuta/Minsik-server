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
    db_max_overflow: int = pydantic.Field(default=10)

    redis_host: str = pydantic.Field(default="localhost")
    redis_port: int = pydantic.Field(default=6379)
    redis_db: int = pydantic.Field(default=0)
    redis_password: str = pydantic.Field(default="")
    redis_max_connections: int = pydantic.Field(default=20)

    books_service_host: str = pydantic.Field(default="0.0.0.0")
    books_grpc_port: int = pydantic.Field(default=50055)

    cache_book_detail_ttl: int = pydantic.Field(default=3600)
    cache_author_detail_ttl: int = pydantic.Field(default=3600)
    cache_author_books_ttl: int = pydantic.Field(default=1800)
    cache_search_ttl: int = pydantic.Field(default=900)
    cache_popular_ttl: int = pydantic.Field(default=21600)
    cache_category_top_books_ttl: int = pydantic.Field(default=93600)
    cache_genre_bubble_ttl: int = pydantic.Field(default=21600)

    category_cache_refresh_enabled: bool = pydantic.Field(default=True)
    category_cache_refresh_cron: str = pydantic.Field(default="0 7 * * *")

    view_count_flush_enabled: bool = pydantic.Field(default=True)
    view_count_flush_cron: str = pydantic.Field(default="*/5 * * * *")
    view_count_flush_batch_size: int = pydantic.Field(default=100)

    search_default_limit: int = pydantic.Field(default=10)
    search_max_limit: int = pydantic.Field(default=100)
    search_author_books_expansion: int = pydantic.Field(default=3)

    es_host: str = pydantic.Field(default="elasticsearch")
    es_port: int = pydantic.Field(default=9200)
    es_index_books: str = pydantic.Field(default="books")
    es_index_authors: str = pydantic.Field(default="authors")
    es_index_series: str = pydantic.Field(default="series")
    es_reindex_enabled: bool = pydantic.Field(default=True)
    es_reindex_cron: str = pydantic.Field(default="0 5,11,17,23 * * *")
    es_reindex_batch_size: int = pydantic.Field(default=1000)

    ledger_api_key: str = pydantic.Field(default="")

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
