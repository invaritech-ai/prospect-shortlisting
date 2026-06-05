from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.api.routes.full_pipeline import list_full_pipeline_companies
from app.models import Campaign, ClassificationResult, Contact, ScrapeResult, UploadedDomain
from app.models.base import utcnow


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _domain(
    campaign_id,
    domain: str,
    *,
    scrape_status: str | None = "succeeded",
    fetch_status: str | None = None,
    created_at: datetime | None = None,
) -> UploadedDomain:
    return UploadedDomain(
        id=uuid4(),
        campaign_id=campaign_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        dedupe_key=domain,
        scrape_status=scrape_status,
        fetch_status=fetch_status,
        created_at=created_at or utcnow(),
    )


def test_full_pipeline_companies_returns_paged_rows_with_server_side_stage_summaries(db_session: Session) -> None:
    campaign = Campaign(id=uuid4(), name="Full Pipeline")
    now = utcnow()
    alpha = _domain(
        campaign.id,
        "alpha.example",
        fetch_status="succeeded",
        created_at=now - timedelta(days=2),
    )
    beta = _domain(
        campaign.id,
        "beta.example",
        scrape_status="failed",
        created_at=now - timedelta(days=2),
    )
    other_campaign_domain = _domain(uuid4(), "alpha-other.example", fetch_status="succeeded")
    db_session.add_all([campaign, alpha, beta, other_campaign_domain])
    db_session.commit()

    db_session.add_all(
        [
            ScrapeResult(
                campaign_id=campaign.id,
                domain_id=alpha.id,
                state="succeeded",
                updated_at=now - timedelta(hours=2),
                final_url="https://alpha.example/about",
            ),
            ScrapeResult(
                campaign_id=campaign.id,
                domain_id=beta.id,
                state="failed",
                updated_at=now - timedelta(hours=1),
                error_code="timeout",
                failure_class="network",
                retryable=True,
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=alpha.id,
                state="succeeded",
                predicted_label="crap",
                manual_label="possible",
                created_at=now - timedelta(hours=1),
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=beta.id,
                state="succeeded",
                predicted_label="unknown",
                created_at=now - timedelta(hours=1),
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=alpha.id,
                first_name="Fresh",
                last_name="Valid",
                selected_email="Fresh@Alpha.example",
                verified_email_snapshot="fresh@alpha.example",
                verification_status="valid",
                verification_applied=True,
                verified_at=now - timedelta(days=1),
                updated_at=now - timedelta(minutes=30),
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=alpha.id,
                first_name="Stale",
                last_name="Valid",
                selected_email="stale@alpha.example",
                verified_email_snapshot="stale@alpha.example",
                verification_status="valid",
                verification_applied=True,
                verified_at=now - timedelta(days=31),
                updated_at=now - timedelta(minutes=20),
            ),
            Contact(
                campaign_id=campaign.id,
                domain_id=alpha.id,
                first_name="No",
                last_name="Email",
                selected_email=None,
                updated_at=now - timedelta(minutes=10),
            ),
        ]
    )
    db_session.commit()

    out = list_full_pipeline_companies(
        campaign_id=campaign.id,
        search="alpha",
        limit=50,
        offset=0,
        session=db_session,
    )

    assert out.total == 1
    assert out.limit == 50
    assert out.offset == 0
    assert len(out.items) == 1
    row = out.items[0]
    assert row.domain_id == alpha.id
    assert row.domain == "alpha.example"
    assert row.scrape_status == "succeeded"
    assert row.latest_scrape_final_url == "https://alpha.example/about"
    assert row.effective_label == "possible"
    assert row.classification_state == "succeeded"
    assert row.fetch_status == "succeeded"
    assert row.contacts_found == 3
    assert row.emails_found == 2
    assert row.email_contact_count == 2
    assert row.valid_email_count == 1
    assert row.last_activity == now - timedelta(minutes=10)


def test_full_pipeline_companies_paginates_domains_before_aggregating(db_session: Session) -> None:
    campaign = Campaign(id=uuid4(), name="Paged Full Pipeline")
    first = _domain(campaign.id, "a-first.example", fetch_status="succeeded")
    second = _domain(campaign.id, "b-second.example", fetch_status="succeeded")
    db_session.add_all([campaign, first, second])
    db_session.commit()
    db_session.add(
        Contact(
            campaign_id=campaign.id,
            domain_id=first.id,
            first_name="Only",
            last_name="First",
            selected_email="first@example.com",
        )
    )
    db_session.commit()

    out = list_full_pipeline_companies(
        campaign_id=campaign.id,
        limit=1,
        offset=1,
        session=db_session,
    )

    assert out.total == 2
    assert [row.domain for row in out.items] == ["b-second.example"]
    assert out.items[0].contacts_found == 0
