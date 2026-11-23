"""Settings loaded from environment variables / .env (pydantic-settings)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Missing .env is fine: defaults keep tests runnable offline.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_timeout: int = 60  # seconds per LLM request; a stalled provider must not hang the app
    llm_retries: int = 2  # litellm retries on 429/503 with backoff
    llm_fallback_model: str = ""  # used only if the main model keeps failing (503, timeout)
    judge_model: str = ""  # model for the eval LLM-judge; empty = same as llm_model
    logfire_token: str = ""
    daily_limit: int = 200
    rate_limit: str = "10/minute"
    # Cross-encoder logits below this mean "evidence is weak". 0.0 is only a placeholder:
    # calibrate it on real queries in Phase 4 (answerable vs unanswerable scores).
    cors_origins: str = ""  # comma-separated; empty = same-origin only (locked down)
    github_url: str = ""  # shown in the UI header when set
    weak_score_threshold: float = 0.0


def llm_kwargs(settings: Settings) -> dict:
    """Connection arguments shared by every litellm.completion call."""
    kwargs: dict = {
        "api_key": settings.llm_api_key or None,
        "timeout": settings.llm_timeout,
        "num_retries": settings.llm_retries,
        # Some models reject parameters such as temperature; drop those instead of failing.
        "drop_params": True,
    }
    if settings.llm_fallback_model:
        kwargs["fallbacks"] = [settings.llm_fallback_model]  # tried after retries are used up
    return kwargs


def get_settings() -> Settings:
    return Settings()
