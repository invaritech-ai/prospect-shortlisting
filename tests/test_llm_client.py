from __future__ import annotations

import json

from app.services.llm_client import LLMClient


class _FakeResponse:
    def __init__(self, payload: dict, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001,ANN201
        return False


def test_chat_with_usage_parses_openrouter_metadata(monkeypatch) -> None:
    payload = {
        "id": "req_123",
        "choices": [{"message": {"content": "hello"}}],
        "usage": {
            "prompt_tokens": 111,
            "completion_tokens": 222,
            "cost": 0.0123,
        },
    }

    def _fake_urlopen(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        return _FakeResponse(
            payload=payload,
            headers={
                "x-request-id": "req_hdr_789",
                "x-openrouter-generation-id": "gen_456",
            },
        )

    monkeypatch.setattr("app.services.llm_client.urlopen", _fake_urlopen)

    client = LLMClient(purpose="test")
    client._api_key = "test-key"  # noqa: SLF001
    content, error, usage = client.chat_with_usage(
        model="openai/gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hello"}],
    )

    assert content == "hello"
    assert error == ""
    assert usage["provider"] == "openrouter"
    assert usage["model"] == "openai/gpt-4o-mini"
    assert usage["request_id"] == "req_hdr_789"
    assert usage["openrouter_generation_id"] == "gen_456"
    assert usage["prompt_tokens"] == 111
    assert usage["completion_tokens"] == 222
    assert usage["billed_cost_usd"] == 0.0123
    assert usage["raw_usage"]["prompt_tokens"] == 111
