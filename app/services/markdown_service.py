from __future__ import annotations

import hashlib
import json

import html2text

from app.services import credentials_resolver
from app.services.llm_client import LLMClient
from app.services.redis_client import get_redis
from app.services.url_utils import clean_text

# Minimum meaningful chars from rule-based conversion before we try LLM.
_MIN_RULE_BASED_CHARS = 300
_MARKDOWN_CACHE_TTL = 86400  # 24 hours

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
    def __init__(self) -> None:
        self._client = None
        self._init_error = ""
        # Presence check only — actual LLM calls go through LLMClient which
        # resolves the key dynamically from the DB-first/env-fallback store.
        self._openai_key = ""
        self._openrouter_key = credentials_resolver.resolve("openrouter", "api_key")
        self._cache_enabled = True
        self._init_openai_client()

    def _init_openai_client(self) -> None:
        """Compatibility hook for tests and older call sites."""
        return None

    def _call_openrouter(
        self,
        *,
        url: str,
        title: str,
        page_text: str,
        model: str,
    ) -> tuple[str, str]:
        return _markdown_llm.chat(
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

    def _llm_unavailable_error(self) -> str:
        if getattr(self, "_init_error", ""):
            return str(self._init_error)
        openrouter_key = credentials_resolver.resolve("openrouter", "api_key") or getattr(self, "_openrouter_key", "")
        if not getattr(self, "_openai_key", "") and not openrouter_key:
            return "llm_api_key_missing"
        return ""

    def _assemble_rule_based(self, url: str, title: str, rule_md: str, page_text: str) -> str:
        """Build final rule-based markdown from an already-converted string."""
        md = rule_md or clean_text(page_text)[:18000]
        header = f"# {title or 'Untitled'}\n\nSource: {url}\n\n"
        return (header + md).strip() or "_No text extracted._"

    def _cache_key(self, page_text: str) -> str:
        digest = hashlib.sha256(page_text[:20000].encode()).hexdigest()[:16]
        return f"md_llm:{digest}"

    def _cache_get(self, key: str) -> str | None:
        if not getattr(self, "_cache_enabled", False):
            return None
        redis = get_redis()
        if not redis:
            return None
        try:
            val = redis.get(key)
            return val.decode("utf-8") if val else None
        except Exception:  # noqa: BLE001
            return None

    def _cache_set(self, key: str, value: str) -> None:
        if not getattr(self, "_cache_enabled", False):
            return
        redis = get_redis()
        if not redis:
            return
        try:
            redis.setex(key, _MARKDOWN_CACHE_TTL, value)
        except Exception:  # noqa: BLE001
            pass

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
        LLM results are cached in Redis by content hash for 24h.
        """
        rule_md = _html_to_markdown(page_text)

        if len(rule_md) >= _MIN_RULE_BASED_CHARS:
            header = f"# {title or 'Untitled'}\n\nSource: {url}\n\n"
            return (header + rule_md).strip(), False, ""

        # Check cache before calling LLM
        cache_key = self._cache_key(page_text)
        cached = self._cache_get(cache_key)
        if cached:
            return cached, True, ""

        llm_unavailable_error = self._llm_unavailable_error()
        if llm_unavailable_error:
            return self._assemble_rule_based(url, title, rule_md, page_text), False, llm_unavailable_error

        # Rule-based output too thin — try LLM.
        content, error = self._call_openrouter(url=url, title=title, page_text=page_text, model=model)
        if content:
            self._cache_set(cache_key, content)
            return content, True, ""
        # Reuse already-computed rule_md — no second _html_to_markdown call.
        return self._assemble_rule_based(url, title, rule_md, page_text), False, error or "llm_call_failed"

    def to_markdown_batch(
        self,
        *,
        pages: list[dict],  # each: {url, title, page_text}
        model: str,
    ) -> list[tuple[str, bool, str]]:
        """Convert multiple pages to markdown in a single LLM call.

        Rule-based conversion is tried first for each page. Only pages whose
        rule-based output is too thin are batched into one LLM call.
        Results are cached in Redis by content hash for 24h.

        Returns a list of (markdown, used_llm, error_code) in input order.
        Falls back to per-page to_markdown() if the batch call fails.
        """
        if not pages:
            return []

        results: list[tuple[str, bool, str] | None] = [None] * len(pages)
        needs_llm: list[tuple[int, dict, str]] = []  # (original_index, page, rule_md)

        # Phase 1: rule-based + cache check
        for i, page in enumerate(pages):
            page_text = page.get("page_text", "")
            url = page.get("url", "")
            title = page.get("title", "")
            rule_md = _html_to_markdown(page_text)

            if len(rule_md) >= _MIN_RULE_BASED_CHARS:
                header = f"# {title or 'Untitled'}\n\nSource: {url}\n\n"
                results[i] = (header + rule_md).strip(), False, ""
                continue

            # Check cache
            cache_key = self._cache_key(page_text)
            cached = self._cache_get(cache_key)
            if cached:
                results[i] = cached, True, ""
                continue

            needs_llm.append((i, page, rule_md))

        if not needs_llm:
            return results  # type: ignore[return-value]

        # Phase 2: batch LLM call for remaining pages
        # Cap total input to ~60k chars; split into batches if needed
        _MAX_BATCH_CHARS = 60000
        batches: list[list[tuple[int, dict, str]]] = []
        current_batch: list[tuple[int, dict, str]] = []
        current_chars = 0
        for item in needs_llm:
            page_chars = len(item[1].get("page_text", "")[:20000])
            if current_batch and current_chars + page_chars > _MAX_BATCH_CHARS:
                batches.append(current_batch)
                current_batch = [item]
                current_chars = page_chars
            else:
                current_batch.append(item)
                current_chars += page_chars
        if current_batch:
            batches.append(current_batch)

        for batch in batches:
            batch_results = self._run_batch(batch, model)
            for (orig_idx, page, rule_md), result in zip(batch, batch_results):
                if result is not None:
                    results[orig_idx] = result
                    # Cache successful LLM results
                    if result[1]:  # used_llm
                        self._cache_set(self._cache_key(page.get("page_text", "")), result[0])
                else:
                    # Fallback: assemble from rule_md
                    results[orig_idx] = self._assemble_rule_based(
                        page.get("url", ""), page.get("title", ""), rule_md, page.get("page_text", "")
                    ), False, "llm_batch_failed"

        return results  # type: ignore[return-value]

    def _run_batch(
        self,
        batch: list[tuple[int, dict, str]],
        model: str,
    ) -> list[tuple[str, bool, str] | None]:
        """Send one LLM call for a batch of pages, parse delimited response."""
        _DELIM = "===PAGE_{n}==="

        sections: list[str] = []
        for n, (_, page, _) in enumerate(batch):
            sections.append(
                f"{_DELIM.format(n=n)}\n"
                f"URL: {page.get('url', '')}\n"
                f"TITLE: {page.get('title', '')}\n\n"
                f"{page.get('page_text', '')[:20000]}"
            )

        user_content = (
            "Convert each webpage section below to clean content-only markdown.\n"
            "Keep headings, lists, and tables. Remove nav/footer/cookie boilerplate. Do not add facts.\n"
            f"Return each section's markdown preceded by its delimiter (e.g. {_DELIM.format(n=0)}).\n\n"
            + "\n\n".join(sections)
        )

        content, error = _markdown_llm.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You convert webpage extractions to markdown. Return each page's markdown, delimited exactly as instructed.",
                },
                {"role": "user", "content": user_content},
            ],
        )

        if error or not content:
            return [None] * len(batch)

        # Parse: split on delimiters
        import re
        delimiter_pattern = re.compile(r"===PAGE_(\d+)===")
        parts = delimiter_pattern.split(content)
        # parts = ["preamble", "0", "markdown_0", "1", "markdown_1", ...]
        parsed: dict[int, str] = {}
        for j in range(1, len(parts) - 1, 2):
            try:
                idx = int(parts[j])
                parsed[idx] = parts[j + 1].strip()
            except (ValueError, IndexError):
                continue

        if len(parsed) != len(batch):
            # Parsing failed — fall back to None (caller will use rule-based)
            return [None] * len(batch)

        out: list[tuple[str, bool, str] | None] = []
        for n in range(len(batch)):
            md = parsed.get(n)
            if md:
                out.append((md, True, ""))
            else:
                out.append(None)
        return out
