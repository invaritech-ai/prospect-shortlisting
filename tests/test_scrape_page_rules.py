from __future__ import annotations

from app.services.link_service import apply_page_selection_rules


def test_apply_page_selection_rules_ignores_legacy_page_kind_allowlist() -> None:
    targets = {
        "home": "https://example.com",
        "about": "https://example.com/about",
        "contact": "https://example.com/contact",
        "services": "https://example.com/services",
    }
    rules = {
        "page_kinds": ["home", "contact"],
        "fallback_enabled": True,
        "fallback_limit": 1,
        "fallback_priority": ["services", "about"],
    }

    assert apply_page_selection_rules(targets=targets, rules=rules) == targets


def test_apply_page_selection_rules_no_rules_returns_targets() -> None:
    targets = {"home": "https://example.com", "contact": "https://example.com/contact"}
    assert apply_page_selection_rules(targets=targets, rules=None) == targets
