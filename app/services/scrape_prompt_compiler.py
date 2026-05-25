from __future__ import annotations

from typing import Any


def build_scrape_rules_snapshot(
    *,
    instruction_text: str | None,
    structured_rules: dict[str, Any] | None,
    default_rules: dict[str, Any],
) -> dict[str, Any]:
    """Package human scrape instructions into worker-readable settings."""
    snapshot = dict(default_rules)
    if structured_rules:
        snapshot.update({
            key: value
            for key, value in structured_rules.items()
            if key not in {"page_kinds", "fallback_priority"}
        })

    instruction = (instruction_text or "").strip()
    if instruction:
        snapshot["classifier_prompt_text"] = instruction
    else:
        snapshot.pop("classifier_prompt_text", None)

    snapshot.pop("page_kinds", None)
    snapshot.pop("fallback_priority", None)
    return snapshot
