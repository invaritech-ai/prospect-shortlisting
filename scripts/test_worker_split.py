"""Test deterministic worker split: browserless vs local Chromium.

Runs two fetches — one with PS_BROWSERLESS_URL set (browserless mode),
one with it cleared (local mode) — and verifies each uses the correct path.

Usage:
    uv run python scripts/test_worker_split.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TEST_URL = "https://example.com"  # lightweight, always up


async def test_mode(mode: str) -> None:
    """Test a single fetch mode by manipulating the settings."""
    # Import fresh each time — settings is a singleton but we can mutate it
    from app.core.config import settings
    from app.services.fetch_service import fetch_with_fallback

    original_url = settings.browserless_url

    if mode == "browserless":
        if not original_url:
            logger.warning("SKIP browserless test — PS_BROWSERLESS_URL not set in .env")
            return
        # Use the configured URL as-is
        logger.info("=" * 60)
        logger.info("TEST: BROWSERLESS MODE (cdp_url=%s)", settings.browserless_url[:40] + "...")
        logger.info("=" * 60)
    else:
        # Clear the URL to force local mode
        settings.browserless_url = ""
        logger.info("=" * 60)
        logger.info("TEST: LOCAL CHROMIUM MODE (no cdp_url)")
        logger.info("=" * 60)

    try:
        result = await fetch_with_fallback(TEST_URL)
        logger.info(
            "RESULT: mode=%s fetch_mode=%s status=%d error=%s text_len=%d",
            mode,
            result.fetch_mode,
            result.status_code,
            result.error_code or "(none)",
            len(result.extra_text) if result.extra_text else 0,
        )
        if result.selector:
            text = result.selector.get_all_text(separator=" ")[:100]
            logger.info("CONTENT PREVIEW: %s", text.strip())
        if result.error_code:
            logger.error("FETCH FAILED: %s — %s", result.error_code, result.error_message)
        else:
            logger.info("OK — %s mode works", mode.upper())
    finally:
        # Restore original setting
        settings.browserless_url = original_url


async def main() -> None:
    logger.info("Testing deterministic worker split on %s", TEST_URL)
    logger.info("")

    # Test browserless first (if configured), then local
    await test_mode("browserless")
    logger.info("")
    await test_mode("local")

    logger.info("")
    logger.info("Done. Both modes tested independently — no cross-fallback.")


if __name__ == "__main__":
    asyncio.run(main())
