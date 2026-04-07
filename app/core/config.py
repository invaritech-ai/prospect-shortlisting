from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "prospect-shortlisting-scraper"
    database_url: str = "sqlite:///data/scrape_service.db"
    general_model: str = "openai/gpt-5-nano"
    classify_model: str = "inception/mercury-2"
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "https://local.prospect-shortlisting"
    openrouter_app_name: str = "prospect-shortlisting-scraper"
    redis_url: str = "redis://127.0.0.1:6379/0"
    upload_file_ttl_hours: int = 24
    scrape_static_timeout_sec: float = 12.0
    scrape_stealth_timeout_ms: int = 120000  # 2 min — CAPTCHA solving + slow pages
    markdown_model: str = "stepfun/step-3.5-flash"
    # Browserless CDP URL, e.g. wss://production-sfo.browserless.io?token=YOUR_TOKEN
    # When set, the stealth fetch tier connects to this remote real-Chrome instance
    # instead of launching a local headless Chromium.
    browserless_url: str | None = None
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    snov_client_id: str = ""
    snov_client_secret: str = ""
    apollo_api_key: str = ""
    zerobounce_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PS_",
        extra="ignore",
    )


settings = Settings()
