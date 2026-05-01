from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Company, Contact, TitleMatchRule, Upload
from app.models.pipeline import utcnow

_TITLE_SYNONYMS: dict[str, str] = {
    "vp": "vice president",
    "svp": "senior vice president",
    "evp": "executive vice president",
    "avp": "assistant vice president",
    "cmo": "chief marketing officer",
    "cto": "chief technology officer",
    "cio": "chief information officer",
    "cdo": "chief digital officer",
    "coo": "chief operating officer",
    "cfo": "chief financial officer",
    "cro": "chief revenue officer",
    "cpo": "chief product officer",
    "ceo": "chief executive officer",
    "gm": "general manager",
}

SENIORITY_PRESETS: dict[str, list[str]] = {
    "c_level": ["chief", "ceo", "cto", "cmo", "coo", "cfo", "cdo", "cio", "cro", "cpo"],
    "vp_level": ["vice president", "vp", "svp", "evp"],
    "director_level": ["director"],
    "manager_level": ["manager"],
    "senior_ic": ["senior", "lead", "principal", "staff"],
}

SEED_INCLUDE_RULES: list[str] = [
    "marketing, director",
    "marketing, vp",
    "marketing, vice president",
    "chief marketing officer",
    "marketing head",
    "owner",
    "founder",
    "cmo",
    "gm",
    "general manager",
    "e-commerce",
    "ecommerce",
    "IT, director",
    "IT, vp",
    "IT, vice president",
    "chief digital officer",
    "cdo",
    "chief technology officer",
    "cto",
    "cio",
    "chief information officer",
    "webmaster",
    "digital marketing, director",
    "digital marketing, vp",
]

SEED_EXCLUDE_RULES: list[str] = [
    "representative",
    "associate",
    "executive",
    "assistant",
]


def normalize_title(title: str) -> str:
    normalized = (title or "").lower()
    for abbreviation, replacement in _TITLE_SYNONYMS.items():
        normalized = re.sub(r"\b" + re.escape(abbreviation) + r"\b", replacement, normalized)
    return normalized


def match_title(
    title: str,
    include_rules: list[list[str]],
    exclude_words: list[str],
) -> bool:
    if not title:
        return False
    lowered = normalize_title(title)
    normalized_excludes = [normalize_title(word.strip()) for word in exclude_words if word.strip()]
    if any(re.search(r"\b" + re.escape(word) + r"\b", lowered) for word in normalized_excludes):
        return False
    for keywords in include_rules:
        if len(keywords) == 1 and keywords[0].startswith("__regex__:"):
            pattern = keywords[0][len("__regex__:"):]
            if re.search(pattern, lowered, re.IGNORECASE):
                return True
        elif all(re.search(r"\b" + re.escape(normalize_title(kw)) + r"\b", lowered) for kw in keywords):
            return True
    return False


def load_title_rules(
    session: Session,
    *,
    campaign_id: UUID,
) -> tuple[list[list[str]], list[str]]:
    rules = list(
        session.exec(
            select(TitleMatchRule)
            .where(col(TitleMatchRule.campaign_id) == campaign_id)
            .order_by(col(TitleMatchRule.rule_type), col(TitleMatchRule.created_at))
        )
    )
    include_rules: list[list[str]] = []
    exclude_words: list[str] = []
    for rule in rules:
        match_type = (rule.match_type or "keyword").strip().lower()
        if rule.rule_type == "include":
            if match_type == "regex":
                include_rules.append([f"__regex__:{rule.keywords.strip()}"])
            elif match_type == "seniority":
                for keyword in SENIORITY_PRESETS.get(rule.keywords.strip(), []):
                    include_rules.append([normalize_title(keyword)])
            else:
                keywords = [normalize_title(part.strip()) for part in rule.keywords.split(",") if part.strip()]
                if keywords:
                    include_rules.append(keywords)
        elif rule.rule_type == "exclude":
            exclude_words.extend(
                normalize_title(part.strip())
                for part in rule.keywords.split(",")
                if part.strip()
            )
    return include_rules, exclude_words


def rematch_contacts(session: Session, *, campaign_id: UUID) -> int:
    include_rules, exclude_words = load_title_rules(session, campaign_id=campaign_id)
    contacts = list(
        session.exec(
            select(Contact)
            .join(Company, col(Company.id) == col(Contact.company_id))
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(col(Upload.campaign_id) == campaign_id)
        )
    )
    updated = 0
    now = utcnow()
    for contact in contacts:
        new_match = match_title(contact.title or "", include_rules, exclude_words) if include_rules else False
        if contact.title_match == new_match:
            continue
        contact.title_match = new_match
        has_email = bool((contact.email or "").strip())
        if has_email and contact.title_match and contact.verification_status == "valid":
            contact.pipeline_stage = "campaign_ready"
        elif has_email:
            contact.pipeline_stage = "email_revealed"
        else:
            contact.pipeline_stage = "fetched"
        contact.updated_at = now
        session.add(contact)
        updated += 1
    if updated:
        session.commit()
    return updated


def seed_title_rules(session: Session, *, campaign_id: UUID) -> int:
    existing = {
        (rule.rule_type, rule.match_type, rule.keywords)
        for rule in session.exec(
            select(TitleMatchRule).where(col(TitleMatchRule.campaign_id) == campaign_id)
        )
    }
    inserted = 0
    for keywords in SEED_INCLUDE_RULES:
        key = ("include", "keyword", keywords)
        if key in existing:
            continue
        session.add(
            TitleMatchRule(
                campaign_id=campaign_id,
                rule_type="include",
                keywords=keywords,
                match_type="keyword",
            )
        )
        inserted += 1
    for keywords in SEED_EXCLUDE_RULES:
        key = ("exclude", "keyword", keywords)
        if key in existing:
            continue
        session.add(
            TitleMatchRule(
                campaign_id=campaign_id,
                rule_type="exclude",
                keywords=keywords,
                match_type="keyword",
            )
        )
        inserted += 1
    session.commit()
    return inserted


def compute_title_rule_stats(session: Session, *, campaign_id: UUID) -> dict[str, Any]:
    rules = list(
        session.exec(
            select(TitleMatchRule)
            .where(col(TitleMatchRule.campaign_id) == campaign_id)
            .order_by(col(TitleMatchRule.rule_type), col(TitleMatchRule.created_at))
        )
    )
    raw_titles = [
        title
        for title in session.exec(
            select(Contact.title)
            .join(Company, col(Company.id) == col(Contact.company_id))
            .join(Upload, col(Upload.id) == col(Company.upload_id))
            .where(
                col(Upload.campaign_id) == campaign_id,
                col(Contact.is_active).is_(True),
                col(Contact.title).is_not(None),
            )
        ).all()
        if title
    ]

    # Normalize all titles once — avoids O(N×R) re-normalization inside rule loops
    normalized_titles = [normalize_title(t) for t in raw_titles]

    include_rules, exclude_words = load_title_rules(session, campaign_id=campaign_id)
    total_matched = sum(1 for t in raw_titles if match_title(t, include_rules, exclude_words))

    rule_stats: list[dict[str, Any]] = []
    for rule in rules:
        match_type = (rule.match_type or "keyword").strip().lower()
        if rule.rule_type == "include":
            if match_type == "regex":
                pattern = re.compile(rule.keywords.strip(), re.IGNORECASE)
                count = sum(1 for nt in normalized_titles if pattern.search(nt))
            elif match_type == "seniority":
                preset_kws = [normalize_title(v) for v in SENIORITY_PRESETS.get(rule.keywords.strip(), [])]
                patterns = [re.compile(r"\b" + re.escape(k) + r"\b") for k in preset_kws if k]
                count = sum(1 for nt in normalized_titles if any(p.search(nt) for p in patterns))
            else:
                kws = [normalize_title(p.strip()) for p in rule.keywords.split(",") if p.strip()]
                patterns = [re.compile(r"\b" + re.escape(k) + r"\b") for k in kws]
                count = sum(1 for nt in normalized_titles if kws and all(p.search(nt) for p in patterns))
        else:
            kws = [normalize_title(p.strip()) for p in rule.keywords.split(",") if p.strip()]
            patterns = [re.compile(r"\b" + re.escape(k) + r"\b") for k in kws]
            count = sum(1 for nt in normalized_titles if any(p.search(nt) for p in patterns))
        rule_stats.append(
            {
                "rule_id": rule.id,
                "rule_type": rule.rule_type,
                "keywords": rule.keywords,
                "contact_match_count": count,
            }
        )

    return {
        "rules": rule_stats,
        "total_contacts": len(raw_titles),
        "total_matched": total_matched,
    }


def test_title_match_detailed(
    title: str,
    session: Session,
    *,
    campaign_id: UUID,
) -> dict[str, Any]:
    rules = list(
        session.exec(select(TitleMatchRule).where(col(TitleMatchRule.campaign_id) == campaign_id))
    )
    normalized = normalize_title(title)

    exclude_words: list[str] = []
    for rule in rules:
        if rule.rule_type != "exclude":
            continue
        exclude_words.extend(
            normalize_title(keyword.strip())
            for keyword in rule.keywords.split(",")
            if keyword.strip()
        )

    excluded_by = [
        keyword
        for keyword in exclude_words
        if re.search(r"\b" + re.escape(keyword) + r"\b", normalized)
    ]

    matching_rules: list[str] = []
    if not excluded_by:
        for rule in rules:
            if rule.rule_type != "include":
                continue
            match_type = (rule.match_type or "keyword").strip().lower()
            if match_type == "regex":
                if re.search(rule.keywords.strip(), normalized, re.IGNORECASE):
                    matching_rules.append(f"regex: {rule.keywords}")
            elif match_type == "seniority":
                if any(
                    re.search(r"\b" + re.escape(normalize_title(keyword)) + r"\b", normalized)
                    for keyword in SENIORITY_PRESETS.get(rule.keywords.strip(), [])
                ):
                    matching_rules.append(f"seniority({rule.keywords})")
            else:
                keywords = [normalize_title(keyword.strip()) for keyword in rule.keywords.split(",") if keyword.strip()]
                if keywords and all(
                    re.search(r"\b" + re.escape(keyword) + r"\b", normalized)
                    for keyword in keywords
                ):
                    matching_rules.append(rule.keywords)

    return {
        "matched": bool(matching_rules),
        "matching_rules": matching_rules,
        "excluded_by": excluded_by,
        "normalized_title": normalized,
    }
