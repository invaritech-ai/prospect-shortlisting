from __future__ import annotations

import pytest

from app.services.scrape_intent_formatter import default_scrape_rules, format_scrape_intent_to_rules


def test_formatter_returns_defaults_for_empty_intent() -> None:
    rules, err = format_scrape_intent_to_rules("   ")
    assert err == ""
    assert rules == default_scrape_rules()


def test_formatter_validates_llm_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.scrape_intent_formatter._scrape_intent_llm.chat",
        lambda **_: ('{"page_kinds":["pricing","products"],"fallback_limit":2}', ""),
    )
    rules, err = format_scrape_intent_to_rules("Find pricing and product pages")
    assert err == ""
    assert rules["page_kinds"] == ["pricing", "products"]
    assert rules["fallback_limit"] == 2
    assert rules["fallback_enabled"] is True


def test_formatter_falls_back_to_defaults_on_parse_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.scrape_intent_formatter._scrape_intent_llm.chat",
        lambda **_: ("not-json", ""),
    )
    rules, err = format_scrape_intent_to_rules("some intent")
    assert err == "scrape_intent_parse_failed"
    assert rules == default_scrape_rules()
