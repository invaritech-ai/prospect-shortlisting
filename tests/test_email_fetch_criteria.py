from __future__ import annotations

from app.services.email_fetch_criteria import EmailFetchCriteria, provider_title_hints, title_matches_criteria


def test_comma_rule_requires_all_parts_in_any_order() -> None:
    criteria = EmailFetchCriteria(include_titles=["marketing, director"], exclude_titles=[])

    assert title_matches_criteria("Director of Marketing", criteria) is True


def test_exclude_rule_overrides_include_match() -> None:
    criteria = EmailFetchCriteria(include_titles=["marketing director"], exclude_titles=["assistant"])

    assert title_matches_criteria("Assistant Marketing Director", criteria) is False


def test_title_synonyms_match_common_abbreviations() -> None:
    criteria = EmailFetchCriteria(include_titles=["chief marketing officer"], exclude_titles=[])

    assert title_matches_criteria("CMO", criteria) is True


def test_provider_title_hints_use_specific_phrase_without_changing_local_contract() -> None:
    criteria = EmailFetchCriteria(include_titles=["marketing, director", "chief marketing officer"], exclude_titles=[])

    assert provider_title_hints(criteria) == ["marketing", "chief marketing officer"]
