from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "prospect-shortlisting-scraper"
    database_url: str = "sqlite:///data/scrape_service.db"
    general_model: str = "openai/gpt-5-nano"
    classify_model: str = "inception/mercury-2"
    ocr_model: str = "google/gemini-3.1-flash-lite-preview"
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "https://local.prospect-shortlisting"
    openrouter_app_name: str = "prospect-shortlisting-scraper"
    max_images_per_page: int = 8
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_queue_key: str = "prospect:jobs"
    worker_block_timeout_sec: int = 5
    worker_cleanup_interval_sec: int = 900
    upload_file_ttl_hours: int = 24
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PS_",
        extra="ignore",
    )


settings = Settings()
