from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlmodel import SQLModel, Session, create_engine

import app.models.classification  # noqa: F401
import app.models.core  # noqa: F401
import app.models.scrape  # noqa: F401
from app.api.routes.analysis import get_ai_review_domain_analysis, list_ai_review_domains
from app.api.routes.analysis import get_ai_review_label_counts, get_ai_review_letter_counts
from app.models.classification import ClassificationResult
from app.models.core import Campaign, UploadedDomain


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_ai_review_domains_returns_only_scraped_campaign_rows() -> None:
    with _make_session() as session:
        c1 = Campaign(id=uuid4(), name="C1")
        c2 = Campaign(id=uuid4(), name="C2")
        session.add(c1)
        session.add(c2)
        d1 = UploadedDomain(
            id=uuid4(),
            campaign_id=c1.id,
            upload_id=None,
            raw_url="https://a.com",
            normalized_url="https://a.com",
            domain="a.com",
            dedupe_key="a.com",
            scrape_status="succeeded",
        )
        d2 = UploadedDomain(
            id=uuid4(),
            campaign_id=c1.id,
            upload_id=None,
            raw_url="https://b.com",
            normalized_url="https://b.com",
            domain="b.com",
            dedupe_key="b.com",
            scrape_status="failed",
        )
        d3 = UploadedDomain(
            id=uuid4(),
            campaign_id=c2.id,
            upload_id=None,
            raw_url="https://c.com",
            normalized_url="https://c.com",
            domain="c.com",
            dedupe_key="c.com",
            scrape_status="succeeded",
        )
        session.add(d1)
        session.add(d2)
        session.add(d3)
        session.commit()

        out = list_ai_review_domains(
            campaign_id=c1.id,
            letter=None,
            label=None,
            search=None,
            session=session,
            limit=50,
            offset=0,
        )
        assert out.total == 1
        assert len(out.items) == 1
        assert out.items[0].domain == "a.com"


def test_ai_review_domains_includes_unclassified_scraped_domains() -> None:
    with _make_session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        session.add(campaign)
        d1 = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            upload_id=None,
            raw_url="https://x.com",
            normalized_url="https://x.com",
            domain="x.com",
            dedupe_key="x.com",
            scrape_status="succeeded",
        )
        session.add(d1)
        session.commit()

        out = list_ai_review_domains(
            campaign_id=campaign.id,
            letter=None,
            label=None,
            search=None,
            session=session,
            limit=50,
            offset=0,
        )
        assert out.total == 1
        assert out.items[0].classification_result_id is None
        assert out.items[0].effective_label is None


def test_ai_review_domains_uses_latest_and_manual_override() -> None:
    with _make_session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            upload_id=None,
            raw_url="https://z.com",
            normalized_url="https://z.com",
            domain="z.com",
            dedupe_key="z.com",
            scrape_status="succeeded",
        )
        session.add(campaign)
        session.add(domain)
        session.commit()

        t0 = datetime.now(timezone.utc) - timedelta(minutes=2)
        t1 = datetime.now(timezone.utc) - timedelta(minutes=1)

        r_old = ClassificationResult(
            id=uuid4(),
            campaign_id=campaign.id,
            domain_id=domain.id,
            state="succeeded",
            predicted_label="possible",
            confidence=Decimal("0.9000"),
            reasoning_json={"summary": "old"},
            evidence_json={"pages": ["p1"]},
            created_at=t0,
        )
        r_new = ClassificationResult(
            id=uuid4(),
            campaign_id=campaign.id,
            domain_id=domain.id,
            state="succeeded",
            predicted_label="crap",
            confidence=Decimal("0.3000"),
            manual_label="possible",
            manual_comment="manual override",
            manually_reviewed_at=t1,
            reasoning_json={"summary": "new"},
            evidence_json={"pages": ["p1", "p2"]},
            created_at=t1,
        )
        session.add(r_old)
        session.add(r_new)
        session.commit()

        out = list_ai_review_domains(
            campaign_id=campaign.id,
            letter=None,
            label=None,
            search=None,
            session=session,
            limit=50,
            offset=0,
        )
        row = out.items[0]
        assert row.predicted_label == "crap"
        assert row.effective_label == "possible"
        assert row.confidence == Decimal("0.3000")
        assert row.effective_confidence == Decimal("0.3000")
        assert row.manual_comment == "manual override"


def test_ai_review_letter_counts_are_scraped_campaign_only() -> None:
    with _make_session() as session:
        c1 = Campaign(id=uuid4(), name="C1")
        c2 = Campaign(id=uuid4(), name="C2")
        session.add(c1)
        session.add(c2)
        rows = [
            UploadedDomain(
                id=uuid4(),
                campaign_id=c1.id,
                upload_id=None,
                raw_url="https://alpha.com",
                normalized_url="https://alpha.com",
                domain="alpha.com",
                dedupe_key="alpha.com",
                scrape_status="succeeded",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=c1.id,
                upload_id=None,
                raw_url="https://beta.com",
                normalized_url="https://beta.com",
                domain="beta.com",
                dedupe_key="beta.com",
                scrape_status="succeeded",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=c1.id,
                upload_id=None,
                raw_url="https://1numeric.com",
                normalized_url="https://1numeric.com",
                domain="1numeric.com",
                dedupe_key="1numeric.com",
                scrape_status="succeeded",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=c1.id,
                upload_id=None,
                raw_url="https://also-a.com",
                normalized_url="https://also-a.com",
                domain="also-a.com",
                dedupe_key="also-a.com",
                scrape_status="failed",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=c2.id,
                upload_id=None,
                raw_url="https://alpha-other.com",
                normalized_url="https://alpha-other.com",
                domain="alpha-other.com",
                dedupe_key="alpha-other.com",
                scrape_status="succeeded",
            ),
        ]
        session.add_all(rows)
        session.commit()

        out = get_ai_review_letter_counts(campaign_id=c1.id, session=session)
        assert out.counts == {"A": 1, "B": 1, "#": 1}


def test_ai_review_label_counts_and_filter_use_effective_label() -> None:
    with _make_session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        session.add(campaign)
        domains = [
            UploadedDomain(
                id=uuid4(),
                campaign_id=campaign.id,
                upload_id=None,
                raw_url="https://possible.com",
                normalized_url="https://possible.com",
                domain="possible.com",
                dedupe_key="possible.com",
                scrape_status="succeeded",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=campaign.id,
                upload_id=None,
                raw_url="https://manual.com",
                normalized_url="https://manual.com",
                domain="manual.com",
                dedupe_key="manual.com",
                scrape_status="succeeded",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=campaign.id,
                upload_id=None,
                raw_url="https://none.com",
                normalized_url="https://none.com",
                domain="none.com",
                dedupe_key="none.com",
                scrape_status="succeeded",
            ),
            UploadedDomain(
                id=uuid4(),
                campaign_id=campaign.id,
                upload_id=None,
                raw_url="https://unknown.com",
                normalized_url="https://unknown.com",
                domain="unknown.com",
                dedupe_key="unknown.com",
                scrape_status="succeeded",
            ),
        ]
        session.add_all(domains)
        session.commit()
        session.add(
            ClassificationResult(
                id=uuid4(),
                campaign_id=campaign.id,
                domain_id=domains[0].id,
                state="succeeded",
                predicted_label="possible",
                confidence=Decimal("0.9000"),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            ClassificationResult(
                id=uuid4(),
                campaign_id=campaign.id,
                domain_id=domains[1].id,
                state="succeeded",
                predicted_label="crap",
                manual_label="possible",
                confidence=Decimal("0.4000"),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            ClassificationResult(
                id=uuid4(),
                campaign_id=campaign.id,
                domain_id=domains[3].id,
                state="succeeded",
                predicted_label="unknown",
                confidence=Decimal("0.5000"),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        counts = get_ai_review_label_counts(campaign_id=campaign.id, letter=None, search=None, session=session)
        assert counts.all == 4
        assert counts.unclassified == 1
        assert counts.possible == 2
        assert counts.unknown == 1
        assert counts.crap == 0

        filtered = list_ai_review_domains(
            campaign_id=campaign.id,
            letter=None,
            label="possible",
            search=None,
            session=session,
            limit=50,
            offset=0,
        )
        assert filtered.total == 2
        assert {row.domain for row in filtered.items} == {"manual.com", "possible.com"}

        unclassified = list_ai_review_domains(
            campaign_id=campaign.id,
            letter=None,
            label="unclassified",
            search=None,
            session=session,
            limit=50,
            offset=0,
        )
        assert unclassified.total == 1
        assert unclassified.items[0].domain == "none.com"

        unknown = list_ai_review_domains(
            campaign_id=campaign.id,
            letter=None,
            label="unknown",
            search=None,
            session=session,
            limit=50,
            offset=0,
        )
        assert unknown.total == 1
        assert unknown.items[0].domain == "unknown.com"


def test_ai_review_domain_analysis_returns_latest_classification_detail() -> None:
    with _make_session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            upload_id=None,
            raw_url="https://detail.com",
            normalized_url="https://detail.com",
            domain="detail.com",
            dedupe_key="detail.com",
            scrape_status="succeeded",
        )
        session.add(campaign)
        session.add(domain)
        session.commit()

        old_created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        latest_created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.add(
            ClassificationResult(
                id=uuid4(),
                campaign_id=campaign.id,
                domain_id=domain.id,
                state="succeeded",
                predicted_label="crap",
                confidence=Decimal("0.1200"),
                reasoning_json={"summary": "old"},
                evidence_json={"evidence": ["old evidence"]},
                created_at=old_created_at,
            )
        )
        latest = ClassificationResult(
            id=uuid4(),
            campaign_id=campaign.id,
            domain_id=domain.id,
            state="succeeded",
            predicted_label="possible",
            confidence=Decimal("0.9200"),
            reasoning_json={
                "priority_score": 85,
                "signals": {"manufacturer_terms": True},
                "other_fields": {"products_evidence": "industrial components"},
                "raw_response": "{\"predicted_label\":\"Possible\"}",
            },
            evidence_json={
                "evidence": [
                    "Industrial components (https://detail.com/products)",
                ]
            },
            created_at=latest_created_at,
        )
        session.add(latest)
        session.commit()

        out = get_ai_review_domain_analysis(
            campaign_id=campaign.id,
            domain_id=domain.id,
            session=session,
        )
        assert out.domain == "detail.com"
        assert out.classification_result_id == latest.id
        assert out.predicted_label == "possible"
        assert out.effective_label == "possible"
        assert out.confidence == Decimal("0.9200")
        assert out.reasoning_json == latest.reasoning_json
        assert out.evidence_json == latest.evidence_json


def test_ai_review_domain_analysis_returns_unclassified_domain_detail() -> None:
    with _make_session() as session:
        campaign = Campaign(id=uuid4(), name="C1")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=campaign.id,
            upload_id=None,
            raw_url="https://unclassified.com",
            normalized_url="https://unclassified.com",
            domain="unclassified.com",
            dedupe_key="unclassified.com",
            scrape_status="succeeded",
        )
        session.add(campaign)
        session.add(domain)
        session.commit()

        out = get_ai_review_domain_analysis(
            campaign_id=campaign.id,
            domain_id=domain.id,
            session=session,
        )
        assert out.domain == "unclassified.com"
        assert out.classification_result_id is None
        assert out.effective_label is None
        assert out.reasoning_json is None
        assert out.evidence_json is None


def test_ai_review_domain_analysis_is_campaign_scoped() -> None:
    with _make_session() as session:
        c1 = Campaign(id=uuid4(), name="C1")
        c2 = Campaign(id=uuid4(), name="C2")
        domain = UploadedDomain(
            id=uuid4(),
            campaign_id=c1.id,
            upload_id=None,
            raw_url="https://isolated.com",
            normalized_url="https://isolated.com",
            domain="isolated.com",
            dedupe_key="isolated.com",
            scrape_status="succeeded",
        )
        session.add(c1)
        session.add(c2)
        session.add(domain)
        session.commit()

        try:
            get_ai_review_domain_analysis(
                campaign_id=c2.id,
                domain_id=domain.id,
                session=session,
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("Expected campaign-scoped lookup to return 404")
