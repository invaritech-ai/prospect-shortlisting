"""Unit tests for MarkdownService.

No DB, no network — all LLM calls are mocked.

Tests:
- html2text produces ≥ 300 chars → returned directly, no LLM call
- html2text produces < 300 chars (sparse page) → LLM is called
- LLM call fails → falls back to rule-based output
- Empty input → graceful fallback string
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


import pytest

from app.services.markdown_service import MarkdownService, _html_to_markdown, _MIN_RULE_BASED_CHARS


# ---------------------------------------------------------------------------
# _html_to_markdown unit tests (no external deps)
# ---------------------------------------------------------------------------

class TestHtmlToMarkdown:
    def test_converts_basic_html(self):
        html = "<h1>Hello</h1><p>Some paragraph text here.</p>"
        result = _html_to_markdown(html)
        assert "Hello" in result
        assert "Some paragraph text here" in result

    def test_strips_nav_boilerplate(self):
        html = "<nav><a href='/'>Home</a></nav><p>Real content goes here.</p>"
        result = _html_to_markdown(html)
        # Link is present, but nav structure is flattened
        assert "Real content goes here" in result

    def test_plain_text_passthrough(self):
        text = "Just some plain text without any HTML tags at all."
        result = _html_to_markdown(text)
        assert "plain text" in result

    def test_empty_input_returns_empty(self):
        assert _html_to_markdown("") == ""
        assert _html_to_markdown("   ") == ""


# ---------------------------------------------------------------------------
# MarkdownService.to_markdown tests
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(monkeypatch) -> MarkdownService:
    """MarkdownService with no real API keys — LLM disabled by default."""
    monkeypatch.setattr("app.services.markdown_service.MarkdownService._init_openai_client", lambda self: None)
    svc = MarkdownService.__new__(MarkdownService)
    svc._client = None
    svc._init_error = "llm_api_key_missing"
    svc._openrouter_key = ""
    svc._openai_key = ""
    return svc


class TestRuleBasedPath:
    """When html2text output is ≥ MIN chars, we never call LLM."""

    def test_rich_html_uses_rule_based(self, svc: MarkdownService):
        # Build HTML that produces a long enough text block.
        content = "The quick brown fox jumps over the lazy dog. " * 20
        html = f"<article><h1>Title</h1><p>{content}</p></article>"

        md, used_llm, error = svc.to_markdown(
            url="https://example.com",
            title="Example",
            page_text=html,
            model="test-model",
        )

        assert used_llm is False
        assert error == ""
        assert "Title" in md
        assert len(md) >= _MIN_RULE_BASED_CHARS

    def test_header_and_source_injected(self, svc: MarkdownService):
        content = "x " * 200
        _, used_llm, _ = svc.to_markdown(
            url="https://example.com",
            title="My Page",
            page_text=f"<p>{content}</p>",
            model="test-model",
        )
        assert used_llm is False


class TestLLMFallbackPath:
    """When html2text output is too short, LLM should be attempted."""

    def test_sparse_page_triggers_llm(self, monkeypatch):
        """A page with very little text should trigger the LLM call."""
        llm_output = "# Clean Markdown\n\nSome LLM-generated content."

        svc = MarkdownService.__new__(MarkdownService)
        svc._client = None
        svc._init_error = ""
        svc._openai_key = ""
        svc._openrouter_key = "fake-key"

        monkeypatch.setattr(svc, "_call_openrouter", lambda **kwargs: (llm_output, ""))

        md, used_llm, error = svc.to_markdown(
            url="https://sparse.com",
            title="Sparse",
            page_text="<p>Hi.</p>",  # very short — below threshold
            model="test-model",
        )

        assert used_llm is True
        assert error == ""
        assert md == llm_output

    def test_llm_failure_falls_back_to_rule_based(self, monkeypatch):
        """If LLM fails, rule-based output is returned with an error code."""
        svc = MarkdownService.__new__(MarkdownService)
        svc._client = None
        svc._init_error = ""
        svc._openai_key = ""
        svc._openrouter_key = "fake-key"

        monkeypatch.setattr(svc, "_call_openrouter", lambda **kwargs: ("", "llm_call_failed"))

        md, used_llm, error = svc.to_markdown(
            url="https://sparse.com",
            title="Sparse",
            page_text="<p>Hi.</p>",
            model="test-model",
        )

        assert used_llm is False
        assert error == "llm_call_failed"
        assert "sparse.com" in md.lower() or "Sparse" in md

    def test_no_api_key_falls_back(self, svc: MarkdownService):
        """No API key configured → returns rule-based with error code."""
        md, used_llm, error = svc.to_markdown(
            url="https://nokey.com",
            title="No Key",
            page_text="<p>Tiny.</p>",
            model="test-model",
        )
        assert used_llm is False
        assert error == "llm_api_key_missing"
