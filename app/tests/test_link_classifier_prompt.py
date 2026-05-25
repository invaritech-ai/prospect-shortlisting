from __future__ import annotations

import json
from typing import Any

from app.services import link_service


def test_link_classifier_uses_raw_operator_instruction_with_fixed_keys(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return json.dumps({"about": "https://example.com/company"}), ""

    monkeypatch.setattr(link_service._classify_llm, "chat", fake_chat)

    result = link_service.classify_links_with_llm(
        domain="example.com",
        candidates=["https://example.com/company", "https://example.com/blog/post"],
        model="cheap-model",
        classifier_prompt_text="Include company pages. Exclude blog posts.",
    )

    assert result["about"] == "https://example.com/company"
    user_prompt = captured["messages"][1]["content"]
    assert "Include company pages. Exclude blog posts." in user_prompt
    assert '"about": ""' in user_prompt
    assert '"products": ""' in user_prompt
    assert "fixed internal keys" in user_prompt
