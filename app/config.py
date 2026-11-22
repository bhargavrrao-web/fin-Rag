"""Settings loaded from environment variables / .env (pydantic-settings)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Missing .env is fine: defaults keep tests runnable offline.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    logfire_token: str = ""
    daily_limit: int = 200
    rate_limit: str = "10/minute"


def get_settings() -> Settings:
    return Settings()
