"""AgroPredict Backend - Core Configuration"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Database
    DATABASE_URL: str = "mysql+aiomysql://root:password@localhost:3306/agropredict"

    # For synchronous operations (backfill scripts, etc.)
    @property
    def SYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("aiomysql", "pymysql")

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # data.gov.in
    DATA_GOV_IN_API_KEY: str = ""

    # OpenRouter LLM
    OPENROUTER_API_KEY: str = ""

    # Chronos
    CHRONOS_MODEL_NAME: str = "amazon/chronos-t5-small"

    # FastAPI
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # Notifications (optional)
    SLACK_WEBHOOK_URL: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    NOTIFICATION_EMAIL: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
