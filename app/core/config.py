from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "prospect-shortlisting-scraper"
    database_url: str = Field(
        default="sqlite:///data/scrape_service.db",
        validation_alias=AliasChoices("DATABASE_URL", "PS_DATABASE_URL"),
    )
    general_model: str = "openai/gpt-5-nano"
    classify_model: str = "inception/mercury-2"
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str = "https://local.prospect-shortlisting"
    openrouter_app_name: str = "prospect-shortlisting-scraper"
    upload_file_ttl_hours: int = 24
    scrape_static_timeout_sec: float = 12.0
    scrape_stealth_timeout_ms: int = 120000  # 2 min — CAPTCHA solving + slow pages
    scrape_impersonate_timeout_sec: float = 15.0

    # ── Domain-adaptive fetch policy ────────────────────────────────────────
    # Inter-request delay window per domain (seconds, uniform jitter). The
    # engine enforces *at least* this spacing between calls to the same
    # origin to avoid burst detection when crawling many pages.
    scrape_domain_min_delay_sec: float = 0.4
    scrape_domain_max_delay_sec: float = 1.2
    # Max concurrent in-flight requests per domain. Independent from the
    # Celery worker concurrency so a single worker can still sustain multi-
    # domain throughput without hammering any one origin.
    scrape_domain_max_concurrency: int = 2
    # Backoff policy when the origin signals active pushback (403/429/bot-
    # wall/timeouts). Delay grows by this multiplier on each consecutive
    # failure, capped by `scrape_domain_max_backoff_sec`, and decays back
    # after consecutive successes.
    scrape_domain_backoff_multiplier: float = 2.0
    scrape_domain_max_backoff_sec: float = 30.0
    # After this many consecutive hostile failures a domain is put into a
    # cooldown window where new requests are refused by the policy engine
    # (preserves worker capacity for healthier targets).
    scrape_domain_circuit_threshold: int = 4
    scrape_domain_cooldown_sec: float = 90.0

    # ── Stealth escalation policy ───────────────────────────────────────────
    # Per-worker cap on the number of distinct domains that may be running
    # under the (expensive) stealth tier at once.
    scrape_stealth_max_domains: int = 3
    # Number of consecutive successful static fetches required before a
    # domain escalated to stealth is demoted back to the static tier.
    scrape_stealth_demotion_streak: int = 3

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
    contact_auto_enqueue_enabled: bool = True
    contact_auto_enqueue_max_batch_size: int = 25
    contact_auto_enqueue_max_active_per_run: int = 10
    contact_dispatcher_batch_size: int = 50
    contact_reveal_dispatcher_batch_size: int = 50
    contact_discovery_freshness_days: int = 30
    contact_provider_circuit_threshold: int = 3
    contact_provider_cooldown_sec: int = 120
    contact_provider_retry_delay_sec: int = 60
    # Master key used by the settings secret store to encrypt/decrypt
    # integration credentials stored in the `integration_secrets` table.
    # Must be a valid urlsafe base64-encoded 32-byte Fernet key. If absent,
    # the DB-backed settings are disabled and env fallback is used.
    settings_encryption_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PS_",
        extra="ignore",
    )


settings = Settings()
