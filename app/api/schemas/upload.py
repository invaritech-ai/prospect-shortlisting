from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class UploadValidationError(BaseModel):
    row_number: int = Field(ge=1)
    raw_value: str
    error_code: str
    error_message: str


class UploadRead(BaseModel):
    id: UUID
    filename: str
    checksum: str
    row_count: int
    valid_count: int
    invalid_count: int
    created_at: datetime


class UploadCreateResult(BaseModel):
    upload: UploadRead
    validation_errors: list[UploadValidationError]


class UploadDetail(BaseModel):
    upload: UploadRead
    validation_errors: list[UploadValidationError]


class UploadList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[UploadRead]


class CompanyRead(BaseModel):
    id: UUID
    upload_id: UUID
    raw_url: str
    normalized_url: str
    domain: str
    created_at: datetime


class UploadCompanyList(BaseModel):
    upload_id: UUID
    total: int
    limit: int
    offset: int
    items: list[CompanyRead]


class CompanyListItem(BaseModel):
    id: UUID
    upload_id: UUID
    upload_filename: str
    raw_url: str
    normalized_url: str
    domain: str
    created_at: datetime
    latest_decision: str | None = None
    latest_confidence: Decimal | None = None


class CompanyList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CompanyListItem]


class CompanyDeleteRequest(BaseModel):
    company_ids: list[UUID] = Field(min_length=1)


class CompanyDeleteResult(BaseModel):
    requested_count: int
    deleted_count: int
    deleted_ids: list[UUID]
    missing_ids: list[UUID]
