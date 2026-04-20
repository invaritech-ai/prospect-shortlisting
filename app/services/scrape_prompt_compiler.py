from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PAGE_KIND_ORDER = [
    "home",
    "about",
    "products",
    "contact",
    "team",
    "leadership",
    "services",
    "pricing",
]

PAGE_KIND_PATTERNS: dict[str, tuple[str, ...]] = {
    "home": (r"\bhome(page)?\b", r"\blanding page\b"),
    "about": (r"\babout\b", r"\bour story\b", r"\bcompany info\b"),
    "products": (r"\bproducts?\b", r"\bsolutions?\b", r"\bcatalog\b"),
    "contact": (r"\bcontacts?\b", r"\bget in touch\b", r"\bsupport\b"),
    "team": (r"\bteam\b", r"\bpeople\b", r"\bstaff\b"),
    "leadership": (r"\bleadership\b", r"\bexecutive(s)?\b", r"\bfounders?\b"),
    "services": (r"\bservices?\b", r"\bofferings?\b"),
    "pricing": (r"\bpricing\b", r"\bplans?\b", r"\bcosts?\b"),
}

DEFAULT_PAGE_KINDS = [kind for kind in PAGE_KIND_ORDER if kind != "home"]


@dataclass(frozen=True)
class CompiledScrapePrompt:
    page_kinds: list[str]
    compiled_prompt_text: str
    scrape_rules_structured: dict[str, Any]


def _detect_page_kinds(intent_text: str | None) -> list[str]:
    normalized = (intent_text or "").strip().lower()
    if not normalized:
        return DEFAULT_PAGE_KINDS.copy()
    detected: list[str] = []
    for page_kind in PAGE_KIND_ORDER:
        patterns = PAGE_KIND_PATTERNS[page_kind]
        if any(re.search(pattern, normalized) for pattern in patterns):
            detected.append(page_kind)
    return detected or DEFAULT_PAGE_KINDS.copy()


def _build_classifier_prompt(page_kinds: list[str]) -> str:
    lines = ["Find the best URL for each of these page types:"]
    lines.extend(f"- {kind}" for kind in page_kinds)
    return "\n".join(lines)


def compile_scrape_prompt(intent_text: str | None) -> CompiledScrapePrompt:
    page_kinds = _detect_page_kinds(intent_text)
    compiled_prompt_text = _build_classifier_prompt(page_kinds)
    scrape_rules_structured = {
        "page_kinds": page_kinds,
        "classifier_prompt_text": compiled_prompt_text,
    }
    return CompiledScrapePrompt(
        page_kinds=page_kinds,
        compiled_prompt_text=compiled_prompt_text,
        scrape_rules_structured=scrape_rules_structured,
    )
