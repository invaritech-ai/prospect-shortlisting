from __future__ import annotations

import json
import os
import ssl
from urllib.request import Request, urlopen

from app.core.config import settings
from app.services.url_utils import clean_text


class MarkdownService:
    def __init__(self) -> None:
        self._client = None
        self._init_error = ""
        self._openrouter_key = settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        self._openai_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "").strip()
        self._init_openai_client()

    def _init_openai_client(self) -> None:
        if self._openrouter_key:
            # OpenRouter path is handled directly in _call_openrouter.
            return
        api_key = self._openai_key
        if not api_key:
            self._init_error = "llm_api_key_missing"
            return
        try:
            from openai import OpenAI  # type: ignore

            self._client = OpenAI(api_key=api_key)
        except Exception:  # noqa: BLE001
            self._client = None
            self._init_error = "llm_client_unavailable"

    def _call_openrouter(self, model: str, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
        }
        data = json.dumps(payload).encode("utf-8")
        base = settings.openrouter_base_url.rstrip("/")
        request = Request(
            url=f"{base}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
        )
        try:
            context = ssl.create_default_context()
            with urlopen(request, context=context, timeout=120) as response:  # noqa: S310
                raw = response.read().decode("utf-8", errors="ignore")
            decoded = json.loads(raw)
            content = decoded["choices"][0]["message"]["content"]
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and str(item.get("type", "")) == "text":
                        text_parts.append(str(item.get("text", "")))
                return "\n".join(part for part in text_parts if part).strip(), ""
            return str(content or "").strip(), ""
        except Exception:  # noqa: BLE001
            return "", "llm_call_failed"

    def _fallback_markdown(self, url: str, title: str, content: str, ocr_text: str) -> str:
        lines = [f"# {title or 'Untitled'}", "", f"Source: {url}", ""]
        lines.append(clean_text(content)[:18000] or "_No text extracted._")
        if ocr_text.strip():
            lines.extend(["", "## Image OCR Text", "", clean_text(ocr_text)[:8000]])
        return "\n".join(lines).strip()

    def to_markdown(
        self,
        *,
        url: str,
        title: str,
        page_text: str,
        ocr_text: str,
        model: str,
    ) -> tuple[str, bool, str]:
        system_prompt = (
            "Convert webpage extraction to clean content-only markdown. "
            "Keep headings, lists, and tables where possible. Remove nav/footer/cookie boilerplate. "
            "Do not add facts."
        )
        user_prompt = (
            f"URL: {url}\n"
            f"TITLE: {title}\n\n"
            "PAGE_TEXT:\n"
            f"{page_text[:20000]}\n\n"
            "IMAGE_OCR_TEXT:\n"
            f"{ocr_text[:8000]}\n\n"
            "Return markdown only."
        )

        if self._openrouter_key:
            markdown, error = self._call_openrouter(model=model, system_prompt=system_prompt, user_prompt=user_prompt)
            if markdown:
                return markdown, True, ""
            return self._fallback_markdown(url, title, page_text, ocr_text), False, error or "llm_call_failed"

        if self._client is None:
            return self._fallback_markdown(url, title, page_text, ocr_text), False, self._init_error

        try:
            response = self._client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            output_text = getattr(response, "output_text", "") or ""
            markdown = str(output_text).strip()
            if not markdown:
                return self._fallback_markdown(url, title, page_text, ocr_text), False, "llm_empty_output"
            return markdown, True, ""
        except Exception:  # noqa: BLE001
            return self._fallback_markdown(url, title, page_text, ocr_text), False, "llm_call_failed"
