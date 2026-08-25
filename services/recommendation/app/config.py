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
    recommendation_db_pool_size: int = pydantic.Field(default=10)
    recommendation_db_max_overflow: int = pydantic.Field(default=10)

    redis_host: str = pydantic.Field(default="localhost")
    redis_port: int = pydantic.Field(default=6379)
    redis_db: int = pydantic.Field(default=0)
    redis_password: str = pydantic.Field(default="")
    redis_max_connections: int = pydantic.Field(default=20)

    recommendation_service_host: str = pydantic.Field(default="0.0.0.0")
    recommendation_grpc_port: int = pydantic.Field(default=50056)

    list_default_size: int = pydantic.Field(default=50)
    cache_recommendation_ttl: int = pydantic.Field(default=86400)
    cache_contextual_ttl: int = pydantic.Field(default=21600)
    cache_profile_ttl: int = pydantic.Field(default=86400)
    # 3 days, not 1 — `personal_refresh_cron` runs daily, and a TTL exactly
    # equal to the cron interval means one slow, failed, or restart-skipped
    # run blanks every user's personalized rows for a full day with no
    # fallback. The cache must always outlive several missed cycles.
    cache_personal_ttl: int = pydantic.Field(default=259200)
    cache_personal_contextual_ttl: int = pydantic.Field(default=1800)
    personal_cold_start_threshold: int = pydantic.Field(default=5)
    # How long a "this user actually requested this locale" marker survives.
    # Long-lived and refreshed on every request — this is what lets the cron
    # warm every locale a user switches to, not only their stored
    # preferred_language.
    personal_seen_locale_ttl: int = pydantic.Field(default=2592000)

    home_book_categories: str = pydantic.Field(
        default="most_read,highest_rated,trending_reads,most_wanted,recently_added,user_favorites,classics,best_writing,funniest,most_emotional"
    )
    home_author_categories: str = pydantic.Field(default="top_authors,popular_authors")

    cache_case_pool_ttl: int = pydantic.Field(default=7200)

    general_refresh_enabled: bool = pydantic.Field(default=True)
    general_refresh_cron: str = pydantic.Field(default="0 0 * * *")
    personal_refresh_enabled: bool = pydantic.Field(default=True)
    personal_refresh_cron: str = pydantic.Field(default="0 1 * * *")
    contextual_precompute_enabled: bool = pydantic.Field(default=True)
    contextual_precompute_cron: str = pydantic.Field(default="0 2 * * *")
    case_pool_refresh_enabled: bool = pydantic.Field(default=True)
    case_pool_refresh_cron: str = pydantic.Field(default="30 * * * *")
    book_of_week_enabled: bool = pydantic.Field(default=True)
    book_of_week_cron: str = pydantic.Field(default="30 3 * * 1")

    contextual_precompute_min_ratings: int = pydantic.Field(default=500)
    contextual_cold_ttl: int = pydantic.Field(default=1800)

    available_languages: str = pydantic.Field(default="en")

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
