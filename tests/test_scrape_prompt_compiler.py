from __future__ import annotations

from app.services.scrape_prompt_compiler import build_scrape_rules_snapshot


def test_snapshot_uses_raw_instruction_text_as_classifier_prompt() -> None:
    instruction = "Include about/company pages. Exclude blog, legal, careers, and login."

    snapshot = build_scrape_rules_snapshot(
        instruction_text=instruction,
        structured_rules=None,
        default_rules={"include_sitemap": True, "js_fallback": True},
    )

    assert snapshot["classifier_prompt_text"] == instruction
    assert snapshot["include_sitemap"] is True
    assert snapshot["js_fallback"] is True
    assert "page_kinds" not in snapshot


def test_snapshot_strips_legacy_page_kind_rules() -> None:
    snapshot = build_scrape_rules_snapshot(
        instruction_text="Use the text.",
        structured_rules={
            "page_kinds": ["home", "contact"],
            "fallback_priority": ["about"],
            "include_sitemap": False,
        },
        default_rules={"include_sitemap": True, "js_fallback": True},
    )

    assert snapshot["classifier_prompt_text"] == "Use the text."
    assert snapshot["include_sitemap"] is False
    assert "page_kinds" not in snapshot
    assert "fallback_priority" not in snapshot
