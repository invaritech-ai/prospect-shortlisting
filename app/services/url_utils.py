from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse


SKIP_EXTENSIONS = {
    ".xml",
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".zip",
    ".rar",
    ".7z",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_url_candidates(raw: str) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return []
    chunks = re.split(r"[\s,;]+", value.replace("\n", " ").replace("\t", " "))
    candidates: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        token = chunk.strip()
        if not token:
            continue
        if token.lower() in {"http:/", "https:/", "http://", "https://"}:
            continue
        if "://" not in token:
            token = f"https://{token}"
        parsed = urlparse(token)
        if not parsed.netloc:
            continue
        if token in seen:
            continue
        seen.add(token)
        candidates.append(token)
    return candidates


def is_reasonable_host(netloc: str) -> bool:
    host = (netloc or "").strip().lower()
    if not host:
        return False
    host = host.split("@")[-1]
    host = host.split(":")[0]
    if not host:
        return False
    if any(ch in host for ch in (",", "/", " ")):
        return False
    if host.startswith(".") or host.endswith("."):
        return False
    if "." not in host:
        return False
    return True


def normalize_url(raw: str) -> str:
    candidates = split_url_candidates(raw)
    if not candidates:
        return ""
    for value in candidates:
        parsed = urlparse(value)
        if not parsed.netloc:
            continue
        if not is_reasonable_host(parsed.netloc):
            continue
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path or "/"
        normalized = parsed._replace(
            scheme=(parsed.scheme or "https").lower(),
            netloc=netloc,
            path=path.rstrip("/") or "/",
            params="",
            query=parsed.query,
            fragment="",
        )
        return urlunparse(normalized)
    return ""


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def canonical_internal_url(url: str, domain: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != domain:
        return ""

    path = parsed.path or "/"
    lowered = path.lower()
    if any(lowered.endswith(ext) for ext in SKIP_EXTENSIONS):
        return ""

    canonical = parsed._replace(
        # Canonicalize to https to avoid duplicate crawl records for http/https variants.
        scheme="https",
        netloc=host,
        path=path.rstrip("/") or "/",
        params="",
        query="",
        fragment="",
    )
    return urlunparse(canonical)


def absolute_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)
