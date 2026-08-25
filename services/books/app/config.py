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

    redis_host: str = pydantic.Field(default="localhost")
    redis_port: int = pydantic.Field(default=6379)
    redis_db: int = pydantic.Field(default=0)
    redis_password: str = pydantic.Field(default="")
    redis_max_connections: int = pydantic.Field(default=20)

    books_service_host: str = pydantic.Field(default="0.0.0.0")
    books_grpc_port: int = pydantic.Field(default=50055)
    grpc_max_message_length: int = pydantic.Field(default=32 * 1024 * 1024)

    cache_book_detail_ttl: int = pydantic.Field(default=3600)
    cache_author_detail_ttl: int = pydantic.Field(default=3600)
    cache_author_books_ttl: int = pydantic.Field(default=1800)
    cache_search_ttl: int = pydantic.Field(default=900)
    cache_category_top_books_ttl: int = pydantic.Field(default=93600)
    cache_genre_bubble_ttl: int = pydantic.Field(default=21600)

    available_languages: str = pydantic.Field(default="en")

    category_cache_refresh_enabled: bool = pydantic.Field(default=True)
    category_cache_refresh_cron: str = pydantic.Field(default="0 7 * * *")

    view_count_flush_enabled: bool = pydantic.Field(default=True)
    view_count_flush_cron: str = pydantic.Field(default="*/5 * * * *")

    # Every list surface reads shelf counts from books.work_shelf_counts. The
    # rebuild is one pass over user_data.bookshelves, so it can run often; the
    # book detail page still computes its own counts live, which is where a
    # reader looks for their own shelf change to show up immediately.
    work_shelf_counts_refresh_enabled: bool = pydantic.Field(default=True)
    work_shelf_counts_refresh_cron: str = pydantic.Field(default="*/15 * * * *")

    # Ranking signals ride a `rescore` pass over the text-matched hits,
    # combined with `score_mode: multiply` so they scale the text score
    # proportionally rather than summing into it — this corpus's `dis_max`
    # scores commonly run in the hundreds of thousands, which would swallow
    # any additive rank feature (max ~2.3) without ever moving the ranking.
    # A pivot is the popularity value at which a signal contributes half its
    # boost: `search_popularity_pivot` keeps the search page's popularity
    # tie-break gentle (an averagely-read book already saturates most of it),
    # while `suggest_popularity_pivot` sits much higher so the app-bar dropdown
    # keeps a wide gap between a handful of readers and a six-figure
    # readership instead of both saturating near the same value. A uniform
    # weight on top of a multiplicative combination would cancel out under
    # sorting, so the pivot — not a scalar — is the actual per-surface knob.
    search_popularity_pivot: float = pydantic.Field(default=50.0)
    suggest_popularity_pivot: float = pydantic.Field(default=2000.0)
    search_popularity_boost: float = pydantic.Field(default=1.5)
    search_quality_pivot: float = pydantic.Field(default=3.5)
    search_quality_boost: float = pydantic.Field(default=0.5)
    # Tie-break only: the query text already carries the language the reader
    # wants, so this just favours what they can actually read among equals.
    search_language_boost: float = pydantic.Field(default=0.3)

    es_host: str = pydantic.Field(default="elasticsearch")
    es_port: int = pydantic.Field(default=9200)
    es_index_catalog: str = pydantic.Field(default="catalog")
    es_reindex_enabled: bool = pydantic.Field(default=True)
    es_reindex_cron: str = pydantic.Field(default="0 5,11,17,23 * * *")
    es_reindex_batch_size: int = pydantic.Field(default=1000)
    es_reconcile_enabled: bool = pydantic.Field(default=True)
    es_reconcile_scan_size: int = pydantic.Field(default=1000)

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
