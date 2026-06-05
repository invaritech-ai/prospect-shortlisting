from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import Session, SQLModel, create_engine

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
    )


def test_s1_companies_sort_updated_after_filters_before_pagination(db_session: Session) -> None:
    from app.api.routes.companies import list_domains

    campaign = Campaign(id=uuid4(), name="S1 Sort")
    newest = _domain(campaign.id, "alpha.example")
    older = _domain(campaign.id, "alpine.example")
    wrong_letter = _domain(campaign.id, "beta.example")
    failed = _domain(campaign.id, "apex.example", scrape_status="failed")
    db_session.add_all([campaign, newest, older, wrong_letter, failed])
    db_session.commit()

    now = utcnow()
    db_session.add_all(
        [
            ScrapeResult(campaign_id=campaign.id, domain_id=newest.id, updated_at=now - timedelta(minutes=5)),
            ScrapeResult(campaign_id=campaign.id, domain_id=older.id, updated_at=now - timedelta(hours=2)),
            ScrapeResult(campaign_id=campaign.id, domain_id=wrong_letter.id, updated_at=now),
            ScrapeResult(campaign_id=campaign.id, domain_id=failed.id, updated_at=now + timedelta(minutes=5)),
        ]
    )
    db_session.commit()

    out = list_domains(
        campaign_id=campaign.id,
        scrape_status="done",
        letter="A",
        search=".example",
        sort_by="updated",
        sort_dir="desc",
        limit=1,
        offset=0,
        session=db_session,
    )

    assert out.total == 2
    assert [row.domain for row in out.items] == ["alpha.example"]


def test_s2_ai_review_sort_pages_after_label_filter_before_pagination(db_session: Session) -> None:
    from app.api.routes.analysis import list_ai_review_domains

    campaign = Campaign(id=uuid4(), name="S2 Sort")
    low_pages = _domain(campaign.id, "alpha.example")
    high_pages = _domain(campaign.id, "atlas.example")
    excluded = _domain(campaign.id, "archived.example")
    db_session.add_all([campaign, low_pages, high_pages, excluded])
    db_session.commit()
    db_session.add_all(
        [
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=low_pages.id,
                state="succeeded",
                predicted_label="possible",
                confidence=Decimal("0.5000"),
                evidence_json={"pages": ["home"]},
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=high_pages.id,
                state="succeeded",
                predicted_label="possible",
                confidence=Decimal("0.9000"),
                evidence_json={"pages": ["home", "about", "contact"]},
            ),
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=excluded.id,
                state="succeeded",
                predicted_label="crap",
                confidence=Decimal("0.1000"),
                evidence_json={"pages": ["home", "about", "contact", "careers"]},
            ),
        ]
    )
    db_session.commit()

    out = list_ai_review_domains(
        campaign_id=campaign.id,
        letter="A",
        label="possible",
        search=".example",
        sort_by="pages",
        sort_dir="desc",
        limit=1,
        offset=0,
        session=db_session,
    )

    assert out.total == 2
    assert out.items[0].domain == "atlas.example"
    assert out.items[0].pages_reviewed == 3


def test_s2_ai_review_default_load_paginates_before_mapping(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import analysis

    campaign = Campaign(id=uuid4(), name="S2 Fast Default")
    domains = [_domain(campaign.id, f"company-{idx}.example") for idx in range(3)]
    db_session.add(campaign)
    db_session.add_all(domains)
    db_session.commit()
    db_session.add_all(
        [
            ClassificationResult(
                campaign_id=campaign.id,
                domain_id=domain.id,
                state="succeeded",
                predicted_label="possible",
                confidence=Decimal("0.9000"),
            )
            for domain in domains
        ]
    )
    db_session.commit()

    mapped_count = 0
    original_mapper = analysis._ai_review_domain_row_from_result

    def counted_mapper(row):
        nonlocal mapped_count
        mapped_count += 1
        return original_mapper(row)

    monkeypatch.setattr(analysis, "_ai_review_domain_row_from_result", counted_mapper)

    out = analysis.list_ai_review_domains(
        campaign_id=campaign.id,
        letter=None,
        label=None,
        search=None,
        limit=1,
        offset=0,
        session=db_session,
    )

    assert out.total == 3
    assert len(out.items) == 1
    assert mapped_count == 1


def test_s3_contacts_sort_contact_count_after_possible_scope_before_pagination(db_session: Session) -> None:
    from app.api.routes import email_fetch

    campaign = Campaign(id=uuid4(), name="S3 Sort")
    low_contacts = _domain(campaign.id, "alpha.example", fetch_status="succeeded")
    high_contacts = _domain(campaign.id, "atlas.example", fetch_status="succeeded")
    excluded = _domain(campaign.id, "archived.example", fetch_status="succeeded")
    db_session.add_all([campaign, low_contacts, high_contacts, excluded])
    db_session.add_all(
        [
            ClassificationResult(campaign_id=campaign.id, domain_id=low_contacts.id, state="succeeded", predicted_label="possible"),
            ClassificationResult(campaign_id=campaign.id, domain_id=high_contacts.id, state="succeeded", predicted_label="possible"),
            ClassificationResult(campaign_id=campaign.id, domain_id=excluded.id, state="succeeded", predicted_label="crap"),
            Contact(campaign_id=campaign.id, domain_id=low_contacts.id, first_name="One", last_name="Contact", selected_email="one@alpha.example"),
            Contact(campaign_id=campaign.id, domain_id=high_contacts.id, first_name="First", last_name="Contact", selected_email="first@atlas.example"),
            Contact(campaign_id=campaign.id, domain_id=high_contacts.id, first_name="Second", last_name="Contact", selected_email=None),
            Contact(campaign_id=campaign.id, domain_id=high_contacts.id, first_name="Third", last_name="Contact", selected_email="third@atlas.example"),
        ]
    )
    db_session.commit()

    out = email_fetch.list_email_fetch_companies(
        campaign_id=campaign.id,
        status="all",
        search=".example",
        letter="A",
        sort_by="contacts",
        sort_dir="desc",
        limit=1,
        offset=0,
        session=db_session,
    )

    assert out.total == 2
    assert out.items[0].domain == "atlas.example"
    assert out.items[0].contacts_found == 3


def test_s4_validation_sort_verified_after_status_filter_before_pagination(db_session: Session) -> None:
    from app.api.routes import email_verification

    campaign = Campaign(id=uuid4(), name="S4 Sort")
    domain = _domain(campaign.id, "alpha.example")
    db_session.add_all([campaign, domain])
    db_session.commit()

    now = utcnow()
    old = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Old",
        last_name="Valid",
        selected_email="old@alpha.example",
        verified_email_snapshot="old@alpha.example",
        verification_status="valid",
        verification_applied=True,
        verified_at=now - timedelta(days=5),
    )
    newest = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="New",
        last_name="Valid",
        selected_email="new@alpha.example",
        verified_email_snapshot="new@alpha.example",
        verification_status="valid",
        verification_applied=True,
        verified_at=now - timedelta(days=1),
    )
    pending = Contact(
        campaign_id=campaign.id,
        domain_id=domain.id,
        first_name="Pending",
        last_name="Contact",
        selected_email="pending@alpha.example",
    )
    db_session.add_all([old, newest, pending])
    db_session.commit()

    out = email_verification.list_email_verification_contacts(
        campaign_id=campaign.id,
        status="valid",
        search="alpha",
        letter="A",
        sort_by="verified",
        sort_dir="desc",
        limit=1,
        offset=0,
        session=db_session,
    )

    assert out.total == 2
    assert out.items[0].selected_email == "new@alpha.example"
