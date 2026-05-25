from __future__ import annotations

from app.services.scrape_service import classify_failure


def test_classify_failure_distinguishes_permanent_blocked_and_transient() -> None:
    assert classify_failure("dns_not_resolved") == ("permanent", False)
    assert classify_failure("off_domain_redirect") == ("permanent", False)
    assert classify_failure("access_denied") == ("blocked", False)
    assert classify_failure("bot_protection") == ("blocked", False)
    assert classify_failure("timeout") == ("transient", True)
    assert classify_failure("rate_limited") == ("transient", True)
    assert classify_failure("no_markdown_produced") == ("no_content", False)
