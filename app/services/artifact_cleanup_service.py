from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, col, select

from app.models import ScrapeJob, ScrapePage


logger = logging.getLogger(__name__)
SCREENSHOT_PREFIX = "[SCREENSHOT_PATH] "
CLEANUP_BATCH_SIZE = 200


@dataclass
class CleanupStats:
    pages_scanned: int = 0
    html_snapshots_cleared: int = 0
    screenshot_files_deleted: int = 0
    delete_failures: int = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_screenshot_path(ocr_text: str) -> str:
    for line in (ocr_text or "").splitlines():
        if line.startswith(SCREENSHOT_PREFIX):
            return line[len(SCREENSHOT_PREFIX) :].strip()
    return ""


class ArtifactCleanupService:
    def cleanup_expired_artifacts(self, *, session: Session, ttl_hours: int) -> CleanupStats:
        cutoff = _utcnow() - timedelta(hours=ttl_hours)
        stats = CleanupStats()

        # Process in small batches using a keyset cursor on ScrapePage.id to
        # avoid loading tens of thousands of large text rows into memory at once.
        # Each batch commits independently so the DB connection never has to
        # buffer an unbounded result set.
        last_id = 0
        while True:
            pages = list(
                session.exec(
                    select(ScrapePage)
                    .join(ScrapeJob, ScrapeJob.id == ScrapePage.job_id)
                    .where(
                        col(ScrapePage.id) > last_id,
                        col(ScrapeJob.terminal_state).is_(True),
                        col(ScrapePage.updated_at) < cutoff,
                    )
                    .order_by(col(ScrapePage.id).asc())
                    .limit(CLEANUP_BATCH_SIZE)
                )
            )
            if not pages:
                break

            for page in pages:
                stats.pages_scanned += 1

                if page.html_snapshot:
                    page.html_snapshot = ""
                    stats.html_snapshots_cleared += 1

                screenshot_path = extract_screenshot_path(page.ocr_text)
                if screenshot_path:
                    try:
                        path = Path(screenshot_path)
                        if path.exists():
                            path.unlink()
                            stats.screenshot_files_deleted += 1
                            parent = path.parent
                            if parent.exists() and not any(parent.iterdir()):
                                try:
                                    parent.rmdir()
                                except OSError:
                                    pass
                    except Exception:  # noqa: BLE001
                        stats.delete_failures += 1

                session.add(page)

            session.commit()
            last_id = pages[-1].id

        return stats
