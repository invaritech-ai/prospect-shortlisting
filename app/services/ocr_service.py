from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import ssl
from urllib.request import Request, urlopen

from app.core.config import settings

# OCR_PROMPT = (
#     "Extract all text from this document page and preserve tables in Markdown. "
#     "Return only Markdown."
# )
OCR_PROMPT = (
    "Extract all visible text from this screenshot. "
    "Return plain text only. No markdown, no explanations."
)


class OCRService:
    def __init__(self) -> None:
        self._openrouter_key = (
            settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY", "").strip()
        )

    def _call_openrouter_ocr(
        self, *, model: str, image_reference: str
    ) -> tuple[str, str]:
        if not self._openrouter_key:
            return "", "ocr_api_key_missing"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": OCR_PROMPT,
                        },
                        {"type": "image_url", "image_url": {"url": image_reference}},
                    ],
                }
            ],
            "temperature": 0.0,
        }
        request = Request(
            url=f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
        )
        try:
            with urlopen(
                request, context=ssl.create_default_context(), timeout=120
            ) as response:  # noqa: S310
                raw = response.read().decode("utf-8", errors="ignore")
            decoded = json.loads(raw)
            content = decoded["choices"][0]["message"]["content"]
            if isinstance(content, list):
                text_parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and str(item.get("type", "")) == "text":
                        text_parts.append(str(item.get("text", "")))
                text = "\n".join(part for part in text_parts if part).strip()
            else:
                text = str(content or "").strip()
            if not text:
                return "", "ocr_no_text"
            return text, ""
        except Exception:  # noqa: BLE001
            return "", "ocr_failed"

    def extract_text_from_image_url(
        self, image_url: str, *, model: str
    ) -> tuple[str, str]:
        if not image_url:
            return "", "ocr_empty_url"
        return self._call_openrouter_ocr(model=model, image_reference=image_url)

    def extract_text_from_file(
        self, file_path: str | Path, *, model: str
    ) -> tuple[str, str]:
        path = Path(file_path)
        if not path.exists():
            return "", "ocr_file_missing"
        try:
            raw = path.read_bytes()
            mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
            encoded = base64.b64encode(raw).decode("ascii")
            image_reference = f"data:{mime_type};base64,{encoded}"
            return self._call_openrouter_ocr(
                model=model, image_reference=image_reference
            )
        except Exception:  # noqa: BLE001
            return "", "ocr_failed"
