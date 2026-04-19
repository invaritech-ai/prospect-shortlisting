from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, col, delete

from app.api.routes.companies import get_company_counts, list_companies
from app.models import Company, Upload
from app.models.pipeline import CompanyPipelineStage


def _seed_upload(session: Session, filename: str) -> Upload:
    upload = Upload(filename=filename, checksum=str(uuid4()), valid_count=0, invalid_count=0)
    session.add(upload)
    session.flush()
    return upload


def _seed_company(session: Session, *, upload_id, domain: str) -> Company:
    company = Company(
        upload_id=upload_id,
        raw_url=f"https://{domain}",
        normalized_url=f"https://{domain}",
        domain=domain,
        pipeline_stage=CompanyPipelineStage.UPLOADED,
    )
    session.add(company)
    session.flush()
    return company


def test_list_companies_multi_letters_is_server_filtered(sqlite_session: Session) -> None:
    upload = _seed_upload(sqlite_session, "letters.csv")
    try:
        _seed_company(sqlite_session, upload_id=upload.id, domain="wolf.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="xeno.example")
        _seed_company(sqlite_session, upload_id=upload.id, domain="apple.example")
        sqlite_session.commit()

        response = list_companies(
            session=sqlite_session,
            letters="w,x",
            include_total=True,
            limit=25,
            offset=0,
        )

        assert response.total == 2
        assert {item.domain for item in response.items} == {"wolf.example", "xeno.example"}
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_company_counts_honors_upload_scope(sqlite_session: Session) -> None:
    upload_a = _seed_upload(sqlite_session, "scope-a.csv")
    upload_b = _seed_upload(sqlite_session, "scope-b.csv")
    try:
        _seed_company(sqlite_session, upload_id=upload_a.id, domain="scope-a.example")
        _seed_company(sqlite_session, upload_id=upload_b.id, domain="scope-b.example")
        sqlite_session.commit()

        scoped = get_company_counts(session=sqlite_session, upload_id=upload_a.id)
        scoped_b = get_company_counts(session=sqlite_session, upload_id=upload_b.id)
        unscoped = get_company_counts(session=sqlite_session)

        assert scoped.total == 1
        assert scoped_b.total == 1
        assert unscoped.total >= (scoped.total + scoped_b.total)
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id).in_([upload_a.id, upload_b.id])))
        sqlite_session.exec(delete(Upload).where(col(Upload.id).in_([upload_a.id, upload_b.id])))
        sqlite_session.commit()


def test_list_companies_invalid_sort_by_raises_422(sqlite_session: Session) -> None:
    upload = _seed_upload(sqlite_session, "sort.csv")
    try:
        _seed_company(sqlite_session, upload_id=upload.id, domain="sort.example")
        sqlite_session.commit()

        with pytest.raises(HTTPException) as excinfo:
            list_companies(session=sqlite_session, sort_by="not_a_real_field")
        assert excinfo.value.status_code == 422
        with pytest.raises(HTTPException) as excinfo_dir:
            list_companies(session=sqlite_session, sort_dir="sideways")
        assert excinfo_dir.value.status_code == 422
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()


def test_company_counts_stage_buckets_are_exact(sqlite_session: Session) -> None:
    upload = _seed_upload(sqlite_session, "stages.csv")
    try:
        for domain, stage in [
            ("up.example", CompanyPipelineStage.UPLOADED),
            ("sc.example", CompanyPipelineStage.SCRAPED),
            ("cl.example", CompanyPipelineStage.CLASSIFIED),
            ("cr.example", CompanyPipelineStage.CONTACT_READY),
        ]:
            company = _seed_company(sqlite_session, upload_id=upload.id, domain=domain)
            company.pipeline_stage = stage
            sqlite_session.add(company)
        sqlite_session.commit()

        counts = get_company_counts(session=sqlite_session, upload_id=upload.id)
        assert counts.total == 4
        assert counts.uploaded == 1
        assert counts.scraped == 1
        assert counts.classified == 1
        assert counts.contact_ready == 1
    finally:
        sqlite_session.exec(delete(Company).where(col(Company.upload_id) == upload.id))
        sqlite_session.exec(delete(Upload).where(col(Upload.id) == upload.id))
        sqlite_session.commit()
