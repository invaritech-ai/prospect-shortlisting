from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.email_fetch_criteria import EmailFetchCriteria, provider_title_hints

SNOV_POSITIONS_PER_SEARCH = 10
MAX_SNOV_TITLE_HINT_CHUNKS_PER_DOMAIN = 3


@dataclass(frozen=True)
class ProviderCandidate:
    provider: str
    provider_person_id: str
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    linkedin_url: str | None = None
    raw_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderSearchResult:
    provider: str
    candidates: list[ProviderCandidate]
    error_code: str = ""
    raw_summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderEmailResult:
    provider: str
    email: str = ""
    status: str | None = None
    error_code: str = ""
    raw_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        if not self.email:
            return False
        if self.provider == "apollo":
            return "email_not_unlocked" not in self.email.lower()
        return (self.status or "").lower() in {"valid", "unknown"}


class EmailFetchProvider(Protocol):
    name: str

    def search_candidates(
        self,
        *,
        domain: str,
        criteria: EmailFetchCriteria,
        limit: int,
    ) -> ProviderSearchResult:
        ...

    def fetch_email(
        self,
        *,
        candidate: ProviderCandidate,
        domain: str,
    ) -> ProviderEmailResult:
        ...


def _apollo_candidate(person: dict[str, Any]) -> ProviderCandidate:
    return ProviderCandidate(
        provider="apollo",
        provider_person_id=str(person.get("id") or "").strip(),
        first_name=str(person.get("first_name") or "").strip(),
        last_name=str(person.get("last_name") or "").strip(),
        title=str(person.get("title") or person.get("headline") or "").strip(),
        linkedin_url=person.get("linkedin_url"),
        raw_summary={
            "id": person.get("id"),
            "organization_id": person.get("organization_id"),
            "email_status": person.get("email_status"),
        },
    )


def _snov_candidate(prospect: dict[str, Any], domain: str) -> ProviderCandidate:
    search_url = str(prospect.get("search_emails_start") or "").strip()
    prospect_hash = search_url.rsplit("/", 1)[-1].split("?")[0].strip() if search_url else ""
    person_id = (
        prospect_hash
        or str(prospect.get("id") or prospect.get("hash") or "").strip()
        or f"{prospect.get('first_name', '')}|{prospect.get('last_name', '')}|{domain}"
    )
    return ProviderCandidate(
        provider="snov",
        provider_person_id=person_id,
        first_name=str(prospect.get("first_name") or "").strip(),
        last_name=str(prospect.get("last_name") or "").strip(),
        title=str(prospect.get("position") or prospect.get("title") or "").strip(),
        linkedin_url=prospect.get("source_page"),
        raw_summary={
            "id": prospect.get("id"),
            "hash": prospect_hash,
            "source_page": prospect.get("source_page"),
        },
    )


class ApolloEmailProvider:
    name = "apollo"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from app.services.apollo_client import ApolloClient

            self._client = ApolloClient()
        return self._client

    def search_candidates(
        self,
        *,
        domain: str,
        criteria: EmailFetchCriteria,
        limit: int,
    ) -> ProviderSearchResult:
        candidates: list[ProviderCandidate] = []
        page = 1
        while len(candidates) < limit:
            raw_people = self.client.search_people(
                domain=domain,
                page=page,
                person_titles=provider_title_hints(criteria) or None,
            )
            err = getattr(self.client, "last_error_code", "")
            if err:
                return ProviderSearchResult(provider=self.name, candidates=candidates, error_code=err)
            if not raw_people:
                break
            for person in raw_people:
                candidate = _apollo_candidate(person)
                if candidate.provider_person_id:
                    candidates.append(candidate)
                if len(candidates) >= limit:
                    break
            if len(raw_people) < 100:
                break
            page += 1
        return ProviderSearchResult(provider=self.name, candidates=candidates[:limit])

    def fetch_email(self, *, candidate: ProviderCandidate, domain: str) -> ProviderEmailResult:  # noqa: ARG002
        person = self.client.reveal_email(candidate.provider_person_id)
        err = getattr(self.client, "last_error_code", "") if not person else ""
        if not person:
            return ProviderEmailResult(provider=self.name, error_code=err)
        email = str(person.get("email") or "").strip()
        return ProviderEmailResult(
            provider=self.name,
            email=email,
            status="valid" if email and "email_not_unlocked" not in email.lower() else None,
            raw_summary={"id": person.get("id"), "email": email},
        )


class SnovEmailProvider:
    name = "snov"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from app.services.snov_client import SnovClient

            self._client = SnovClient()
        return self._client

    def search_candidates(
        self,
        *,
        domain: str,
        criteria: EmailFetchCriteria,
        limit: int,
    ) -> ProviderSearchResult:
        _ = limit
        candidates: list[ProviderCandidate] = []
        seen_ids: set[str] = set()
        hints = provider_title_hints(criteria)
        hint_chunks: list[list[str] | None]
        if hints:
            hint_chunks = [
                hints[index : index + SNOV_POSITIONS_PER_SEARCH]
                for index in range(0, len(hints), SNOV_POSITIONS_PER_SEARCH)
            ][:MAX_SNOV_TITLE_HINT_CHUNKS_PER_DOMAIN]
        else:
            hint_chunks = [None]

        searches = 0
        total_returned = 0
        for chunk_index, positions in enumerate(hint_chunks, start=1):
            prospects, total, err = self.client.search_prospects(
                domain,
                page=1,
                positions=positions,
                chunk_index=chunk_index,
                chunk_count=len(hint_chunks),
            )
            searches += 1
            if err:
                return ProviderSearchResult(
                    provider=self.name,
                    candidates=candidates,
                    error_code=err,
                    raw_summary={"searches": searches, "candidates_returned": len(candidates)},
                )
            total_returned += max(int(total or 0), len(prospects))
            for prospect in prospects:
                candidate = _snov_candidate(prospect, domain)
                if candidate.provider_person_id in seen_ids:
                    continue
                seen_ids.add(candidate.provider_person_id)
                candidates.append(candidate)
        return ProviderSearchResult(
            provider=self.name,
            candidates=candidates,
            raw_summary={
                "searches": searches,
                "candidates_returned": len(candidates),
                "provider_total_returned": total_returned,
                "title_hint_chunks": len(hint_chunks),
            },
        )

    def fetch_email(self, *, candidate: ProviderCandidate, domain: str) -> ProviderEmailResult:
        emails, err = self.client.search_prospect_email(candidate.provider_person_id)
        if (not emails or err) and candidate.first_name and candidate.last_name:
            emails, err = self.client.find_email_by_name(candidate.first_name, candidate.last_name, domain)
        if err:
            return ProviderEmailResult(provider=self.name, error_code=err)
        if not emails:
            return ProviderEmailResult(provider=self.name)
        best = min(emails, key=lambda item: {"valid": 0, "unknown": 1}.get(str(item.get("smtp_status") or ""), 2))
        return ProviderEmailResult(
            provider=self.name,
            email=str(best.get("email") or "").strip(),
            status=str(best.get("smtp_status") or "").strip().lower() or None,
            raw_summary=dict(best),
        )
