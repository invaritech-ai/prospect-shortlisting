from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import pandas as pd
import polars as pl
from sqlmodel import Session

from app.models import Company, Upload
from app.services.url_utils import domain_from_url, normalize_url


MAX_VALIDATION_ERRORS = 200
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_URL_FIELD_LEN = 2048
MAX_DOMAIN_FIELD_LEN = 255
MAX_ERROR_VALUE_LEN = 512
HEADER_KEYWORDS = {"domain", "domains", "website", "websites", "url", "urls", "company_website"}


@dataclass
class UploadIssue:
    row_number: int
    raw_value: str
    error_code: str
    error_message: str


class UploadService:
    def create_upload_from_file(
        self,
        *,
        session: Session,
        filename: str,
        raw_bytes: bytes,
    ) -> tuple[Upload, list[UploadIssue]]:
        if not raw_bytes:
            raise ValueError("Uploaded file is empty.")
        if len(raw_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError(f"File too large. Max size is {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")

        ext = self._extension(filename)
        if ext not in {"csv", "txt", "xlsx", "xls"}:
            raise ValueError("Only .csv, .txt, .xlsx or .xls uploads are supported.")

        rows = self._extract_candidate_rows(ext=ext, raw_bytes=raw_bytes)
        checksum = hashlib.sha256(raw_bytes).hexdigest()

        issues: list[UploadIssue] = []
        company_rows: list[tuple[str, str, str, int]] = []
        seen_normalized: set[str] = set()

        for row_number, raw_value in rows:
            raw_url = raw_value.strip()
            normalized = normalize_url(raw_value)
            if not normalized:
                self._append_issue(
                    issues,
                    UploadIssue(
                        row_number=row_number,
                        raw_value=self._truncate_for_error(raw_value),
                        error_code="invalid_url",
                        error_message="Could not parse a valid URL from row.",
                    ),
                )
                continue

            domain = domain_from_url(normalized)
            if not raw_url:
                self._append_issue(
                    issues,
                    UploadIssue(
                        row_number=row_number,
                        raw_value=self._truncate_for_error(raw_value),
                        error_code="invalid_url",
                        error_message="Could not parse a valid URL from row.",
                    ),
                )
                continue
            if len(normalized) > MAX_URL_FIELD_LEN:
                self._append_issue(
                    issues,
                    UploadIssue(
                        row_number=row_number,
                        raw_value=self._truncate_for_error(raw_value),
                        error_code="normalized_url_too_long",
                        error_message="Normalized URL exceeded storage limit.",
                    ),
                )
                continue
            if not domain or len(domain) > MAX_DOMAIN_FIELD_LEN:
                self._append_issue(
                    issues,
                    UploadIssue(
                        row_number=row_number,
                        raw_value=self._truncate_for_error(raw_value),
                        error_code="domain_too_long",
                        error_message="Extracted domain exceeded storage limit.",
                    ),
                )
                continue
            if normalized in seen_normalized:
                self._append_issue(
                    issues,
                    UploadIssue(
                        row_number=row_number,
                        raw_value=self._truncate_for_error(raw_value),
                        error_code="duplicate_url",
                        error_message="Duplicate URL in upload.",
                    ),
                )
                continue

            seen_normalized.add(normalized)
            company_rows.append((raw_url, normalized, domain, row_number))

        upload = Upload(
            filename=filename or "upload",
            checksum=checksum,
            row_count=len(rows),
            valid_count=len(company_rows),
            invalid_count=len(rows) - len(company_rows),
            validation_errors_json=[
                {
                    "row_number": issue.row_number,
                    "raw_value": issue.raw_value,
                    "error_code": issue.error_code,
                    "error_message": issue.error_message,
                }
                for issue in issues
            ],
        )
        session.add(upload)
        session.flush()

        # Insert in batches to avoid accumulating all Company objects in the
        # SQLAlchemy identity map simultaneously (OOM risk for large uploads).
        batch_size = 1000
        for i in range(0, len(company_rows), batch_size):
            for raw_url, normalized_url, domain, source_row_number in company_rows[i : i + batch_size]:
                session.add(
                    Company(
                        upload_id=upload.id,
                        raw_url=raw_url,
                        normalized_url=normalized_url,
                        domain=domain,
                        source_row_number=source_row_number,
                    )
                )
            session.flush()
            session.expire_all()  # Release identity map entries after each batch.

        session.commit()
        session.refresh(upload)
        return upload, issues

    def _extension(self, filename: str) -> str:
        name = (filename or "").strip().lower()
        if "." not in name:
            return ""
        return name.rsplit(".", 1)[1]

    def _extract_candidate_rows(self, *, ext: str, raw_bytes: bytes) -> list[tuple[int, str]]:
        if ext == "csv":
            frame = self._read_csv_frame(raw_bytes)
        elif ext == "txt":
            frame = self._read_txt_frame(raw_bytes)
        else:
            frame = self._read_excel_frame(raw_bytes)

        if frame.height == 0 or frame.width == 0:
            return []

        column_name = self._select_candidate_column(frame)
        if not column_name:
            return []

        rows: list[tuple[int, str]] = []
        for row_number, value in zip(frame["__row_number__"].to_list(), frame[column_name].to_list(), strict=False):
            text = str(value or "").strip()
            if not text:
                continue
            rows.append((int(row_number), text))
        return rows

    def _read_csv_frame(self, raw_bytes: bytes) -> pl.DataFrame:
        try:
            return pl.read_csv(
                io.BytesIO(raw_bytes),
                has_header=True,
                infer_schema_length=1000,
                ignore_errors=True,
                truncate_ragged_lines=True,
            ).with_row_index(name="__row_number__", offset=2)
        except Exception:
            return pl.read_csv(
                io.BytesIO(raw_bytes),
                has_header=False,
                new_columns=["value"],
                infer_schema_length=1000,
                ignore_errors=True,
                truncate_ragged_lines=True,
            ).with_row_index(name="__row_number__", offset=1)

    def _read_txt_frame(self, raw_bytes: bytes) -> pl.DataFrame:
        text = self._decode(raw_bytes)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return pl.DataFrame({"__row_number__": [], "value": []})
        return pl.DataFrame(
            {
                "__row_number__": list(range(1, len(lines) + 1)),
                "value": lines,
            }
        )

    def _read_excel_frame(self, raw_bytes: bytes) -> pl.DataFrame:
        try:
            frame = pd.read_excel(io.BytesIO(raw_bytes), dtype=str)
        except Exception as exc:
            raise ValueError(f"Could not read Excel file: {exc}") from exc

        frame = frame.fillna("")
        if frame.empty:
            return pl.DataFrame({"__row_number__": []})

        # Avoid pl.from_pandas(...) so pyarrow is not required in runtime images.
        columns: list[str] = []
        used: set[str] = set()
        for idx, raw_name in enumerate(frame.columns, start=1):
            base = str(raw_name).strip() or f"column_{idx}"
            name = base
            suffix = 2
            while name in used:
                name = f"{base}_{suffix}"
                suffix += 1
            used.add(name)
            columns.append(name)
        frame.columns = columns

        data: dict[str, list[object]] = {"__row_number__": list(range(2, len(frame) + 2))}
        for column in frame.columns:
            data[column] = frame[column].astype(str).tolist()
        return pl.DataFrame(data)

    def _select_candidate_column(self, frame: pl.DataFrame) -> str:
        data_columns = [column for column in frame.columns if column != "__row_number__"]
        if not data_columns:
            return ""

        header_match = self._header_match(data_columns)
        if header_match:
            return header_match

        best_column = ""
        best_score = -1
        for column in data_columns:
            values = frame[column].to_list()
            score = sum(1 for value in values if normalize_url(str(value or "").strip()))
            if score > best_score:
                best_score = score
                best_column = column

        return best_column if best_score > 0 else data_columns[0]

    def _header_match(self, columns: list[str]) -> str:
        for column in columns:
            token = str(column).strip().lower()
            if token in HEADER_KEYWORDS:
                return column
            if any(keyword in token for keyword in ("domain", "website", "url")):
                return column
        return ""

    def _decode(self, raw_bytes: bytes) -> str:
        try:
            return raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw_bytes.decode("latin-1")

    def _append_issue(self, issues: list[UploadIssue], issue: UploadIssue) -> None:
        if len(issues) < MAX_VALIDATION_ERRORS:
            issues.append(issue)

    def _truncate_for_error(self, raw_value: str) -> str:
        value = raw_value.strip()
        if len(value) <= MAX_ERROR_VALUE_LEN:
            return value
        return f"{value[:MAX_ERROR_VALUE_LEN]}..."
