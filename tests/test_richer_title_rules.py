from __future__ import annotations

import pytest
from sqlmodel import Session

from app.api.routes.contacts import run_title_test
from app.api.schemas.contacts import TitleTestRequest
from app.models import Campaign, TitleMatchRule


def _campaign(session: Session) -> Campaign:
    campaign = Campaign(name="Richer Title Rules")
    session.add(campaign)
    session.flush()
    return campaign


def test_regex_rule_matches(db_session: Session) -> None:
    campaign = _campaign(db_session)
    db_session.add(TitleMatchRule(
        campaign_id=campaign.id,
        rule_type="include",
        keywords=r"^(head|chief|vp|director).*(e-?commerce|digital)",
        match_type="regex",
    ))
    db_session.commit()
    result = run_title_test(TitleTestRequest(campaign_id=campaign.id, title="Head of Digital Commerce"), session=db_session)
    assert result.matched is True


def test_seniority_c_level_matches_ceo(db_session: Session) -> None:
    campaign = _campaign(db_session)
    db_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="c_level", match_type="seniority"))
    db_session.commit()
    result = run_title_test(TitleTestRequest(campaign_id=campaign.id, title="Chief Executive Officer"), session=db_session)
    assert result.matched is True


def test_seniority_vp_level_matches_vice_president(db_session: Session) -> None:
    campaign = _campaign(db_session)
    db_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="vp_level", match_type="seniority"))
    db_session.commit()
    result = run_title_test(TitleTestRequest(campaign_id=campaign.id, title="Vice President of Sales"), session=db_session)
    assert result.matched is True


def test_keyword_still_works_without_match_type(db_session: Session) -> None:
    """Default match_type='keyword' behaviour is unchanged."""
    campaign = _campaign(db_session)
    db_session.add(TitleMatchRule(campaign_id=campaign.id, rule_type="include", keywords="marketing, director"))
    db_session.commit()
    result = run_title_test(TitleTestRequest(campaign_id=campaign.id, title="Director of Marketing"), session=db_session)
    assert result.matched is True
