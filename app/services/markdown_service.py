from __future__ import annotations

import html2text

from app.services.llm_client import LLMClient
from app.services.url_utils import clean_text

# Minimum meaningful chars from rule-based conversion before we try LLM.
_MIN_RULE_BASED_CHARS = 300

_markdown_llm = LLMClient(purpose="markdown")


def _html_to_markdown(html_or_text: str) -> str:
    """Convert HTML (or plain text) to markdown via html2text."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # no line wrapping
    h.unicode_snob = True
    h.skip_internal_links = True
    return h.handle(html_or_text).strip()


class MarkdownService:
    def _rule_based_markdown(self, url: str, title: str, page_text: str) -> str:
        """Primary conversion path: html2text → clean_text fallback."""
        md = _html_to_markdown(page_text)
        if not md:
            md = clean_text(page_text)[:18000]
        header = f"# {title or 'Untitled'}\n\nSource: {url}\n\n"
        return (header + md).strip() or "_No text extracted._"

    def to_markdown(
        self,
        *,
        url: str,
        title: str,
        page_text: str,
        model: str,
    ) -> tuple[str, bool, str]:
        """Convert page text to markdown.

        Returns (markdown, used_llm, error_code).
        Rule-based (html2text) is tried first; LLM is called only when the
        rule-based output is shorter than _MIN_RULE_BASED_CHARS.
        """
        rule_md = _html_to_markdown(page_text)

        if len(rule_md) >= _MIN_RULE_BASED_CHARS:
            header = f"# {title or 'Untitled'}\n\nSource: {url}\n\n"
            return (header + rule_md).strip(), False, ""

        # Rule-based output too thin — try LLM.
        content, error = _markdown_llm.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert webpage extraction to clean content-only markdown. "
                        "Keep headings, lists, and tables where possible. Remove nav/footer/cookie boilerplate. "
                        "Do not add facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"URL: {url}\n"
                        f"TITLE: {title}\n\n"
                        "PAGE_TEXT:\n"
                        f"{page_text[:20000]}\n\n"
                        "Return markdown only."
                    ),
                },
            ],
        )
        if content:
            return content, True, ""
        return self._rule_based_markdown(url, title, page_text), False, error or "llm_call_failed"
