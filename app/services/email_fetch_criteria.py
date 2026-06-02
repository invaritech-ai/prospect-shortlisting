from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models.contacts import RoleFetchCriteria


DEFAULT_TARGET_CONTACTS_PER_COMPANY = 3
DEFAULT_PROVIDER_ORDER = ["apollo", "snov"]

_TITLE_SYNONYMS: dict[str, str] = {
    "vp": "vice president",
    "svp": "senior vice president",
    "evp": "executive vice president",
    "cmo": "chief marketing officer",
    "cto": "chief technology officer",
    "cio": "chief information officer",
    "cdo": "chief digital officer",
    "coo": "chief operating officer",
    "cfo": "chief financial officer",
    "cro": "chief revenue officer",
    "ceo": "chief executive officer",
    "gm": "general manager",
}


@dataclass(frozen=True)
class EmailFetchCriteria:
    include_titles: list[str]
    exclude_titles: list[str]
    target_contacts_per_company: int = DEFAULT_TARGET_CONTACTS_PER_COMPANY
    provider_order: list[str] | None = None

    def normalized_provider_order(self) -> list[str]:
        order = self.provider_order or DEFAULT_PROVIDER_ORDER
        return [provider for provider in order if provider in {"apollo", "snov"}]

    def snapshot(self) -> dict[str, Any]:
        return {
            "include_titles": list(self.include_titles),
            "exclude_titles": list(self.exclude_titles),
            "target_contacts_per_company": self.target_contacts_per_company,
            "provider_order": self.normalized_provider_order(),
        }

    def targeting_snapshot(self) -> dict[str, Any]:
        return {
            "include_titles": [_normalize_rule(title) for title in self.include_titles if title.strip()],
            "exclude_titles": [_normalize_rule(title) for title in self.exclude_titles if title.strip()],
        }

    def targeting_hash(self) -> str:
        payload = json.dumps(self.targeting_snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rule_value(rule: Any) -> str:
    if isinstance(rule, str):
        return rule.strip()
    if isinstance(rule, dict):
        for key in ("title", "value", "keywords", "text"):
            value = str(rule.get(key) or "").strip()
            if value:
                return value
    return ""


def _rules_from_json(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [value for item in raw if (value := _rule_value(item))]
    if isinstance(raw, dict):
        return [value for item in raw.values() if (value := _rule_value(item))]
    return []


def criteria_from_snapshot(snapshot: dict[str, Any] | None) -> EmailFetchCriteria:
    data = snapshot or {}
    target = int(data.get("target_contacts_per_company") or DEFAULT_TARGET_CONTACTS_PER_COMPANY)
    return EmailFetchCriteria(
        include_titles=[str(v).strip() for v in data.get("include_titles") or [] if str(v).strip()],
        exclude_titles=[str(v).strip() for v in data.get("exclude_titles") or [] if str(v).strip()],
        target_contacts_per_company=max(1, min(target, 10)),
        provider_order=[str(v).strip() for v in data.get("provider_order") or DEFAULT_PROVIDER_ORDER],
    )


def load_current_criteria(session: Session, *, campaign_id: UUID) -> tuple[EmailFetchCriteria, RoleFetchCriteria | None]:
    row = session.exec(
        select(RoleFetchCriteria)
        .where(
            col(RoleFetchCriteria.campaign_id) == campaign_id,
            col(RoleFetchCriteria.is_active).is_(True),
        )
        .order_by(col(RoleFetchCriteria.created_at).desc())
        .limit(1)
    ).first()
    if row is None:
        return EmailFetchCriteria(include_titles=[], exclude_titles=[]), None
    criteria = EmailFetchCriteria(
        include_titles=_rules_from_json(row.include_rules_json),
        exclude_titles=_rules_from_json(row.exclude_rules_json),
    )
    return criteria, row


def normalize_title(title: str) -> str:
    normalized = (title or "").lower()
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("-", " ")
    for abbreviation, replacement in _TITLE_SYNONYMS.items():
        normalized = re.sub(r"\b" + re.escape(abbreviation) + r"\b", replacement, normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_rule(value: str) -> str:
    return normalize_title(value).replace(",", " ").strip()


def _rule_parts(rule: str) -> list[str]:
    normalized = normalize_title(rule)
    if "," in normalized:
        return [part.strip() for part in normalized.split(",") if part.strip()]
    return [normalized] if normalized else []


def _matches_rule(title: str, rule: str) -> bool:
    parts = _rule_parts(rule)
    if not parts:
        return False
    return all(re.search(r"\b" + re.escape(part) + r"\b", title) for part in parts)


def title_matches_criteria(title: str, criteria: EmailFetchCriteria) -> bool:
    normalized_title = normalize_title(title)
    if not normalized_title or not criteria.include_titles:
        return False
    if any(_matches_rule(normalized_title, rule) for rule in criteria.exclude_titles):
        return False
    return any(_matches_rule(normalized_title, rule) for rule in criteria.include_titles)


def title_match_status(title: str, criteria: EmailFetchCriteria) -> tuple[str, str]:
    normalized_title = normalize_title(title)
    if not normalized_title or not criteria.include_titles:
        return "not_matched", "Title did not match"
    for rule in criteria.exclude_titles:
        if _matches_rule(normalized_title, rule):
            return "excluded", f"Excluded by {rule}"
    if any(_matches_rule(normalized_title, rule) for rule in criteria.include_titles):
        return "qualified", "Title matched"
    return "not_matched", "Title did not match"


def provider_title_hints(criteria: EmailFetchCriteria) -> list[str]:
    hints: list[str] = []
    for rule in criteria.include_titles:
        parts = _rule_parts(rule)
        if not parts:
            continue
        # Provider filters are OR-like, so use the most specific phrase as a
        # cost-control hint. Local matching remains the source of truth.
        candidate = max(parts, key=len)
        if candidate not in hints:
            hints.append(candidate)
    return hints
