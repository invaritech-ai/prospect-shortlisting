from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "prospect-shortlisting-scraper"
    database_url: str = Field(
        default="sqlite:///data/scrape_service.db",
        validation_alias=AliasChoices("DATABASE_URL", "PS_DATABASE_URL"),
    )
    general_model: str = "openai/gpt-5-nano"
    classify_model: str = "ibm-granite/granite-4.1-8b"
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
    scrape_stealth_max_pages: int = 2
    scrape_stealth_block_images: bool = True
    scrape_stealth_disable_resources: bool = True
    scrape_stealth_humanize: bool = True
    scrape_stealth_os_randomize: bool = True
    scrape_proxy_url: str = ""

    markdown_model: str = "stepfun/step-3.5-flash"
    # Deprecated: no longer used. Stealth fetches are local-only (Scrapling).
    browserless_url: str | None = None
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    snov_client_id: str = ""
    snov_client_secret: str = ""
    apollo_api_key: str = ""
    zerobounce_api_key: str = ""
    db_connect_timeout_sec: int = 10
    db_keepalives: int = 1
    db_keepalives_idle_sec: int = 30
    db_keepalives_interval_sec: int = 10
    db_keepalives_count: int = 3
    db_api_pool_size: int = 8
    db_api_pool_max_overflow: int = 8
    db_api_pool_timeout_sec: int = 20
    db_api_pool_recycle_sec: int = 300
    procrastinate_pool_min_size: int = 1
    procrastinate_pool_max_size: int = 8
    procrastinate_pool_timeout_sec: int = 120
    # Master key used by the settings secret store to encrypt/decrypt
    # integration credentials stored in the `integration_secrets` table.
    # Must be a valid urlsafe base64-encoded 32-byte Fernet key. If absent,
    # the DB-backed settings are disabled and env fallback is used.
    settings_encryption_key: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        if value.startswith("postgres+"):
            return "postgresql+" + value[len("postgres+") :]
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        if value.startswith("postgresql+psycopg2://"):
            return "postgresql+psycopg://" + value[len("postgresql+psycopg2://") :]
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PS_",
        extra="ignore",
    )


settings = Settings()
