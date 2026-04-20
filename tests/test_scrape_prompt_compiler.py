from __future__ import annotations

from app.services.scrape_prompt_compiler import compile_scrape_prompt


def test_compiler_extracts_known_page_kinds() -> None:
    compiled = compile_scrape_prompt("Find pricing, products, and leadership pages first.")
    assert compiled.page_kinds == ["products", "leadership", "pricing"]
    assert "Find the best URL for each of these page types:" in compiled.compiled_prompt_text
    assert "- products" in compiled.compiled_prompt_text
    assert "- leadership" in compiled.compiled_prompt_text
    assert "- pricing" in compiled.compiled_prompt_text
    assert compiled.scrape_rules_structured["classifier_prompt_text"] == compiled.compiled_prompt_text


def test_compiler_defaults_when_no_keywords_found() -> None:
    compiled = compile_scrape_prompt("Find the pages that matter most for sales qualification.")
    assert compiled.page_kinds == [
        "about",
        "products",
        "contact",
        "team",
        "leadership",
        "services",
        "pricing",
    ]
    assert "- home" not in compiled.compiled_prompt_text


def test_compiler_detects_plural_contacts_keyword() -> None:
    compiled = compile_scrape_prompt("Find homepage and contacts.")
    assert compiled.page_kinds == ["home", "contact"]
    assert "- home" in compiled.compiled_prompt_text
    assert "- contact" in compiled.compiled_prompt_text
