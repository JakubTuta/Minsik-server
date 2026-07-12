import pydantic
import pydantic_settings


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

    ingestion_service_host: str = pydantic.Field(default="0.0.0.0")
    ingestion_grpc_port: int = pydantic.Field(default=50054)

    open_library_api_url: str = pydantic.Field(default="https://openlibrary.org")
    open_library_rate_limit: int = pydantic.Field(default=50)

    google_books_api_url: str = pydantic.Field(default="https://www.googleapis.com/books/v1")
    google_books_api_key: str = pydantic.Field(default="")

    request_timeout: float = pydantic.Field(default=30.0)

    ingestion_max_retries: int = pydantic.Field(default=3)
    ingestion_retry_delay: int = pydantic.Field(default=5)

    continuous_fetch_enabled: bool = pydantic.Field(default=True)
    continuous_ol_cron: str = pydantic.Field(default="0 * * * *")
    continuous_ol_books_per_run: int = pydantic.Field(default=100)
    continuous_gb_cron: str = pydantic.Field(default="0 4,10,16,22 * * *")
    continuous_gb_books_per_run: int = pydantic.Field(default=40)

    description_enrich_enabled: bool = pydantic.Field(default=True)
    description_enrich_cron: str = pydantic.Field(default="30 */2 * * *")
    description_enrich_batch_size: int = pydantic.Field(default=50)
    description_min_length: int = pydantic.Field(default=100)

    ol_dump_base_url: str = pydantic.Field(default="https://openlibrary.org/data")
    dump_batch_size: int = pydantic.Field(default=500)
    dump_tmp_dir: str = pydantic.Field(default="/tmp")
    dump_commit_interval: int = pydantic.Field(default=5000)
    dump_edition_batch_size: int = pydantic.Field(default=500)
    dump_editions_enabled: bool = pydantic.Field(default=True)
    dump_ratings_enabled: bool = pydantic.Field(default=True)
    dump_reading_log_enabled: bool = pydantic.Field(default=True)
    dump_wikidata_enabled: bool = pydantic.Field(default=True)
    dump_edition_flush_interval: int = pydantic.Field(default=100_000)
    dump_work_min_quality_score: int = pydantic.Field(default=2)
    dump_author_min_quality_score: int = pydantic.Field(default=2)

    cleanup_enabled: bool = pydantic.Field(default=True)
    cleanup_cron: str = pydantic.Field(default="0 3,15 * * *")
    cleanup_book_batch_size: int = pydantic.Field(default=100)
    cleanup_author_batch_size: int = pydantic.Field(default=50)
    cleanup_series_batch_size: int = pydantic.Field(default=500)
    cleanup_genre_batch_size: int = pydantic.Field(default=1000)
    cleanup_book_min_quality_score: int = pydantic.Field(default=7)
    cleanup_book_engagement_threshold: int = pydantic.Field(default=10)
    cleanup_book_min_publication_year: int = pydantic.Field(default=1450)
    cleanup_genre_min_book_count: int = pydantic.Field(default=10)
    cleanup_author_min_books: int = pydantic.Field(default=5)
    cleanup_author_max_books: int = pydantic.Field(default=500)
    cleanup_series_min_books: int = pydantic.Field(default=2)
    cleanup_series_max_books: int = pydantic.Field(default=50)

    cleanup_book_max_title_length: int = pydantic.Field(default=300)
    cleanup_book_ol_min_rating_count: int = pydantic.Field(default=20)
    cleanup_book_ol_min_avg_rating: float = pydantic.Field(default=1.5)
    cleanup_author_spare_enriched: bool = pydantic.Field(default=True)
    cleanup_author_junk_publisher_names: bool = pydantic.Field(default=True)

    description_enrich_cooldown_days: int = pydantic.Field(default=30)
    description_enrich_request_delay: float = pydantic.Field(default=1.0)

    genre_bubble_enabled: bool = pydantic.Field(default=True)
    genre_bubble_cron: str = pydantic.Field(default="0 6 * * 0")
    genre_bubble_min_pair_count: int = pydantic.Field(default=5)

    ledger_api_key: str = pydantic.Field(default="")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


settings = Settings()
