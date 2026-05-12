"""Shared email-reveal logic used by both the merged contact-fetch job and the
standalone S4 retry endpoint.

Both call paths need to take a (provider, person_id, first_name, last_name, domain)
tuple and ask the right provider for an email address. Centralising that lookup
here avoids drift between the two callers.
"""
from __future__ import annotations
from dataclasses import dataclass
from structlog import get_logger

logger = get_logger()

@dataclass
class RevealResult:
    """Outcome of a single email-reveal attempt."""

    email: str = ""
    smtp_status: str | None = None
    raw: dict | None = None
    error_code: str = ""

    @property
    def found(self) -> bool:
        return bool(self.email)


_SMTP_RANK = {"valid": 0, "unknown": 1}


def _best_email(emails: list[dict]) -> dict:
    return min(emails, key=lambda e: _SMTP_RANK.get(e.get("smtp_status", ""), 2))


def smtp_to_confidence(smtp_status: str | None) -> float:
    if smtp_status == "valid":
        return 1.0
    if smtp_status == "unknown":
        return 0.5
    return 0.0


def reveal_email_for_person(
    *,
    provider: str,
    person_id: str,
    first_name: str,
    last_name: str,
    domain: str,
) -> RevealResult:
    """Ask the right provider for an email for this person.

    Returns a `RevealResult`. `email` is empty when the provider returned nothing
    or errored — `error_code` distinguishes the two for callers that care.
    """
    pid = (person_id or "").strip()
    logger.info("reveal_email_for_person", provider=provider, pid=pid[:24], domain=domain)
    if provider == "apollo":
        from app.services.apollo_client import ApolloClient

        apollo = ApolloClient()
        result = apollo.reveal_email(pid) if pid else None
        err = apollo.last_error_code if not result else ""
        if result:
            email_val = str(result.get("email") or "").strip()
            # Apollo returns a placeholder like "email_not_unlocked@domain.com"
            # when the plan can't unlock; treat that as "not revealed".
            if email_val and "email_not_unlocked" not in email_val.lower():
                return RevealResult(
                    email=email_val,
                    smtp_status="valid",
                    raw=result,
                )
        return RevealResult(raw=result or {}, error_code=err)

    if provider == "snov":
        from app.services.snov_client import SnovClient

        snov = SnovClient()
        emails: list[dict] = []
        err = ""
        if pid:
            emails, err = snov.search_prospect_email(pid)
        if (not emails or err) and first_name and last_name:
            emails, err = snov.find_email_by_name(first_name, last_name, domain)
        if err:
            return RevealResult(error_code=err)
        if emails:
            best = _best_email(emails)
            return RevealResult(
                email=str(best.get("email") or ""),
                smtp_status=best.get("smtp_status"),
                raw=best,
            )
        return RevealResult()

    return RevealResult(error_code=f"unknown_provider_{provider}")
