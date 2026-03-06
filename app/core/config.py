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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PS_",
        extra="ignore",
    )


settings = Settings()
