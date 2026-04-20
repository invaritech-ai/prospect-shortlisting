from __future__ import annotations

import json


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001, ANN201
        return False


def test_snov_access_token_refreshes_when_credentials_change(monkeypatch) -> None:
    from app.services import snov_client

    current = {
        "client_id": "old-client-id",
        "client_secret": "old-client-secret",
    }
    requests: list[str] = []

    monkeypatch.setattr(snov_client, "_mem_token", "", raising=False)
    monkeypatch.setattr(snov_client, "_mem_token_expires_at", 0.0, raising=False)
    monkeypatch.setattr(snov_client, "_mem_token_cache_key", "", raising=False)
    monkeypatch.setattr(snov_client, "get_redis", lambda: None)

    def fake_resolve(provider: str, field_name: str) -> str:
        assert provider == "snov"
        return current[field_name]

    def fake_urlopen(req, context=None, timeout=None):  # noqa: ANN001, ANN002, ANN003, ARG001
        requests.append(req.data.decode("utf-8"))
        return _FakeResponse(
            {
                "access_token": f"token-for-{current['client_id']}",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(snov_client.credentials_resolver, "resolve", fake_resolve)
    monkeypatch.setattr(snov_client, "urlopen", fake_urlopen)

    client = snov_client.SnovClient()
    token1, err1 = client._get_access_token()  # noqa: SLF001
    assert err1 == ""
    assert token1 == "token-for-old-client-id"

    current["client_id"] = "new-client-id"
    current["client_secret"] = "new-client-secret"

    token2, err2 = client._get_access_token()  # noqa: SLF001

    assert err2 == ""
    assert token2 == "token-for-new-client-id"
    assert len(requests) == 2
