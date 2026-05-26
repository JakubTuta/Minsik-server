from pydantic import Field
from pydantic_settings import BaseSettings


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
    recommendation_db_pool_size: int = Field(default=10)
    recommendation_db_max_overflow: int = Field(default=20)

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: str = Field(default="")
    redis_max_connections: int = Field(default=20)

    recommendation_service_host: str = Field(default="0.0.0.0")
    recommendation_grpc_port: int = Field(default=50056)

    list_default_size: int = Field(default=50)
    cache_recommendation_ttl: int = Field(default=86400)
    cache_contextual_ttl: int = Field(default=21600)
    cache_profile_ttl: int = Field(default=86400)
    cache_personal_ttl: int = Field(default=86400)
    cache_personal_contextual_ttl: int = Field(default=1800)
    personal_cold_start_threshold: int = Field(default=5)

    home_book_categories: str = Field(
        default="most_read,highest_rated,trending_reads,most_wanted,recently_added,user_favorites,classics,best_writing,funniest,most_emotional"
    )
    home_author_categories: str = Field(default="top_authors,popular_authors")

    cache_case_pool_ttl: int = Field(default=7200)

    general_refresh_enabled: bool = Field(default=True)
    general_refresh_cron: str = Field(default="0 0 * * *")
    personal_refresh_enabled: bool = Field(default=True)
    personal_refresh_cron: str = Field(default="0 1 * * *")
    contextual_precompute_enabled: bool = Field(default=True)
    contextual_precompute_cron: str = Field(default="0 2 * * *")
    case_pool_refresh_enabled: bool = Field(default=True)
    case_pool_refresh_cron: str = Field(default="30 * * * *")
    book_of_week_enabled: bool = Field(default=True)
    book_of_week_cron: str = Field(default="30 3 * * 1")

    contextual_precompute_min_ratings: int = Field(default=500)
    contextual_cold_ttl: int = Field(default=1800)

    available_languages: str = Field(default="en")

    ledger_api_key: str = Field(default="")

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
