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

    case_pool_refresh_hours: int = Field(default=1)
    cache_case_pool_ttl: int = Field(default=7200)

    contextual_precompute_min_ratings: int = Field(default=500)
    contextual_cold_ttl: int = Field(default=1800)

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
