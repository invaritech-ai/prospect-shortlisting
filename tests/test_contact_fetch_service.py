from __future__ import annotations

import inspect


def test_fetch_contacts_task_accepts_job_id() -> None:
    from app.jobs.contact_fetch import fetch_contacts

    fn = getattr(fetch_contacts, "original_func", fetch_contacts)
    sig = inspect.signature(fn)
    assert "contact_fetch_job_id" in sig.parameters
    assert "company_id" not in sig.parameters
