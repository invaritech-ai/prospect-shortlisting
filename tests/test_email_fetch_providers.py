from __future__ import annotations

from app.services.email_fetch_criteria import EmailFetchCriteria
from app.services.email_fetch_providers import SnovEmailProvider


class FakeSnovClient:
    def __init__(self) -> None:
        self.calls: list[list[str] | None] = []

    def search_prospects(
        self,
        domain: str,
        page: int = 1,
        positions: list[str] | None = None,
        chunk_index: int | None = None,
        chunk_count: int | None = None,
    ):  # noqa: ANN001, ARG002
        self.calls.append(positions)
        if positions and "chief technology officer" in positions:
            return [
                {
                    "first_name": "Chris",
                    "last_name": "Tech",
                    "position": "Chief Technology Officer",
                    "search_emails_start": "https://app.snov.io/prospect/snov-cto",
                }
            ], 1, ""
        return [], 0, ""


def test_snov_searches_title_hints_beyond_the_first_ten() -> None:
    client = FakeSnovClient()
    provider = SnovEmailProvider(client=client)
    criteria = EmailFetchCriteria(
        include_titles=[
            "Marketing Director",
            "Sales Director",
            "Operations Director",
            "Product Director",
            "Finance Director",
            "Growth Director",
            "Customer Success Director",
            "Revenue Director",
            "Digital Director",
            "Ecommerce Director",
            "Chief Technology Officer",
            "CTO",
        ],
        exclude_titles=[],
    )

    result = provider.search_candidates(domain="example.com", criteria=criteria, limit=12)

    assert len(client.calls) == 2
    assert client.calls[0] == [
        "marketing director",
        "sales director",
        "operations director",
        "product director",
        "finance director",
        "growth director",
        "customer success director",
        "revenue director",
        "digital director",
        "ecommerce director",
    ]
    assert client.calls[1] == ["chief technology officer"]
    assert [candidate.provider_person_id for candidate in result.candidates] == ["snov-cto"]
    assert result.raw_summary["searches"] == 2


def test_snov_title_hint_searches_are_capped_at_three_chunks() -> None:
    client = FakeSnovClient()
    provider = SnovEmailProvider(client=client)
    criteria = EmailFetchCriteria(
        include_titles=[f"Unique Role {index}" for index in range(1, 41)],
        exclude_titles=[],
    )

    provider.search_candidates(domain="example.com", criteria=criteria, limit=12)

    assert len(client.calls) == 3
