from __future__ import annotations

import pytest
from sqlmodel import Session

from app.api.routes.contacts import run_title_test
from app.api.schemas.contacts import TitleTestRequest
from app.models import TitleMatchRule


def test_regex_rule_matches(sqlite_session: Session) -> None:
    sqlite_session.add(TitleMatchRule(
        rule_type="include",
        keywords=r"^(head|chief|vp|director).*(e-?commerce|digital)",
        match_type="regex",
    ))
    sqlite_session.commit()
    result = run_title_test(TitleTestRequest(title="Head of Digital Commerce"), session=sqlite_session)
    assert result.matched is True


def test_seniority_c_level_matches_ceo(sqlite_session: Session) -> None:
    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="c_level", match_type="seniority"))
    sqlite_session.commit()
    result = run_title_test(TitleTestRequest(title="Chief Executive Officer"), session=sqlite_session)
    assert result.matched is True


def test_seniority_vp_level_matches_vice_president(sqlite_session: Session) -> None:
    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="vp_level", match_type="seniority"))
    sqlite_session.commit()
    result = run_title_test(TitleTestRequest(title="Vice President of Sales"), session=sqlite_session)
    assert result.matched is True


def test_keyword_still_works_without_match_type(sqlite_session: Session) -> None:
    """Default match_type='keyword' behaviour is unchanged."""
    sqlite_session.add(TitleMatchRule(rule_type="include", keywords="marketing, director"))
    sqlite_session.commit()
    result = run_title_test(TitleTestRequest(title="Director of Marketing"), session=sqlite_session)
    assert result.matched is True
