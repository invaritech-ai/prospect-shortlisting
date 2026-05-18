from __future__ import annotations

import hashlib
import io
import logging
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, col, select

from app.api.schemas.upload import DomainList, DomainRead, UploadCreateResult, UploadList, UploadRead
from app.db.session import get_session
from app.models.base import utcnow
from app.models.core import Campaign, Upload, UploadedDomain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["uploads"])

# URL heuristic: has a dot in the right place, no spaces, no @
_URL_PAT = re.compile(r'^(https?://)?[a-zA-Z0-9][\w.-]*\.[a-z]{2,}(/\S*)?$', re.I)


def _looks_like_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    return 3 < len(v) < 512 and ' ' not in v and '@' not in v and bool(_URL_PAT.match(v))


def _normalize(raw: str) -> tuple[str, str, str]:
    """Returns (normalized_url, domain, dedupe_key)."""
    v = raw.strip()
    if not re.match(r'^https?://', v, re.I):
        v = 'https://' + v
    parsed = urlparse(v)
    host = (parsed.hostname or '').lower()
    domain = re.sub(r'^www\.', '', host)
    path = parsed.path.rstrip('/')
    normalized = f"https://{host}{path}"
    return normalized, domain, domain  # dedupe_key == domain


def _extract_urls(content: bytes, filename: str) -> list[str]:
    """Read CSV/XLSX; return one URL-like string per row (first match), file-level deduplicated."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'csv'
    if ext in ('xlsx', 'xls'):
        df = pd.read_excel(io.BytesIO(content), header=None, dtype=str)
    else:
        df = pd.read_csv(io.BytesIO(content), header=None, dtype=str, on_bad_lines='skip')

    urls: list[str] = []
    seen: set[str] = set()
    for _, row in df.iterrows():
        for cell in row:
            if _looks_like_url(cell):
                v = str(cell).strip()
                if v not in seen:
                    seen.add(v)
                    urls.append(v)
                break  # first URL-like cell per row wins
    return urls


@router.post("/uploads", response_model=UploadCreateResult, status_code=status.HTTP_201_CREATED)
async def create_upload(
    campaign_id: UUID = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> UploadCreateResult:
    """Parse a CSV/XLSX of company URLs and bulk-insert into the campaign."""
    content = await file.read()
    filename = file.filename or "upload"
    checksum = hashlib.sha256(content).hexdigest()

    try:
        raw_urls = _extract_urls(content, filename)
    except Exception as exc:
        logger.warning("upload_parse_error filename=%s exc=%s", filename, exc)
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}") from exc

    if not raw_urls:
        raise HTTPException(status_code=422, detail="No URL-like values found in the file.")

    row_count = len(raw_urls)

    # Verify campaign exists
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")

    # Insert Upload record first (get its id)
    upload = Upload(
        campaign_id=campaign_id,
        filename=filename,
        checksum=checksum,
        row_count=row_count,
    )
    session.add(upload)
    session.flush()  # populate upload.id without committing

    # Normalize + in-file deduplicate
    domain_values: list[dict] = []
    seen_dedupe: set[str] = set()
    for raw in raw_urls:
        try:
            normalized, domain, dedupe_key = _normalize(raw)
        except Exception:
            continue
        if dedupe_key in seen_dedupe:
            continue
        seen_dedupe.add(dedupe_key)
        domain_values.append({
            "id": uuid4(),
            "campaign_id": campaign_id,
            "upload_id": upload.id,
            "raw_url": raw,
            "normalized_url": normalized,
            "domain": domain,
            "dedupe_key": dedupe_key,
            "created_at": utcnow(),
        })

    new_count = 0
    if domain_values:
        # Find which dedupe_keys already exist in this campaign
        all_keys = [r["dedupe_key"] for r in domain_values]
        existing_keys: set[str] = set(
            session.exec(
                select(UploadedDomain.dedupe_key).where(
                    col(UploadedDomain.campaign_id) == campaign_id,
                    col(UploadedDomain.dedupe_key).in_(all_keys),
                )
            ).all()
        )
        new_rows = [r for r in domain_values if r["dedupe_key"] not in existing_keys]
        new_count = len(new_rows)

        if new_rows:
            session.execute(
                pg_insert(UploadedDomain.__table__)
                .values(new_rows)
                .on_conflict_do_nothing(constraint="uq_uploaded_domains_campaign_dedupe")
            )

    dupe_count = row_count - new_count

    session.commit()
    session.refresh(upload)

    return UploadCreateResult(
        upload=UploadRead.model_validate(upload),
        new_count=new_count,
        dupe_count=dupe_count,
    )


@router.get("/uploads", response_model=UploadList)
def list_uploads(
    campaign_id: UUID = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> UploadList:
    base_q = select(Upload).where(col(Upload.campaign_id) == campaign_id)
    total = session.exec(select(func.count()).select_from(base_q.subquery())).one()
    items = session.exec(
        base_q.order_by(col(Upload.created_at).desc()).limit(limit).offset(offset)
    ).all()
    return UploadList(total=total, limit=limit, offset=offset, items=list(items))


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    upload_id: UUID,
    session: Session = Depends(get_session),
) -> None:
    upload = session.get(Upload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found.")
    # Preserve domains in the campaign — just sever the upload link
    session.execute(
        update(UploadedDomain)
        .where(col(UploadedDomain.upload_id) == upload_id)
        .values(upload_id=None)
    )
    session.delete(upload)
    session.commit()
