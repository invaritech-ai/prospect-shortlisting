"""Convert plain-English scrape intent into structured ScrapeRules."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.api.schemas.scrape import ScrapeRules
from app.core.config import settings
from app.core.logging import log_event
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Interactive prompt saves should fail fast; don't block UI on long retry chains.
_scrape_intent_llm = LLMClient(
    purpose="scrape_intent_rules",
    max_retries=0,
    default_timeout=20,
)


def default_scrape_rules() -> dict[str, Any]:
    """Return safe scraping defaults when no/invalid intent is available."""
    return ScrapeRules().model_dump(exclude_none=True)


def format_scrape_intent_to_rules(intent_text: str | None) -> tuple[dict[str, Any], str]:
    """Convert user intent text into validated scrape rules.

    Returns ``(rules, formatter_error_code)`` where error code is empty on success.
    If conversion fails for any reason, safe defaults are returned.
    """
    normalized_intent = (intent_text or "").strip()
    if not normalized_intent:
        return default_scrape_rules(), ""

    content, llm_error = _scrape_intent_llm.chat(
        model=settings.classify_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You convert plain-English website scraping intent into strict JSON rules. "
                    "Output only valid JSON. Never include markdown fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Given this intent, produce scraping rules.\n\n"
                    f"Intent:\n{normalized_intent}\n\n"
                    "Allowed enum values for page_kinds/fallback_priority: "
                    "home, about, products, contact, team, leadership, services, pricing.\n\n"
                    "Return JSON object with optional keys only from:\n"
                    "- page_kinds: array of allowed enum values\n"
                    "- fallback_enabled: boolean\n"
                    "- fallback_limit: integer between 0 and 3\n"
                    "- fallback_priority: array of allowed enum values\n"
                    "- js_fallback: boolean or null\n"
                    "- include_sitemap: boolean or null\n\n"
                    "Prefer conservative defaults. If uncertain, use minimal safe settings."
                ),
            },
        ],
        response_format={"type": "json_object"},
    )
    if llm_error:
        return default_scrape_rules(), llm_error

    try:
        parsed = json.loads(content) if content else {}
        validated = ScrapeRules.model_validate(parsed)
        # Keep the payload compact and API-compatible.
        return validated.model_dump(exclude_none=True), ""
    except Exception as exc:  # noqa: BLE001
        log_event(
            logger,
            "scrape_intent_rules_parse_failed",
            error=str(exc),
            intent_len=len(normalized_intent),
        )
        return default_scrape_rules(), "scrape_intent_parse_failed"
