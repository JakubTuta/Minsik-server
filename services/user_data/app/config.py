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

    user_data_service_host: str = Field(default="0.0.0.0")
    user_data_grpc_port: int = Field(default=50053)

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def listen_address(self) -> str:
        return f"{self.user_data_service_host}:{self.user_data_grpc_port}"


settings = Settings()
