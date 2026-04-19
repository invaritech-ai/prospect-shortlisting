from __future__ import annotations

import pytest

from app.services.idempotency_service import (
    IdempotencyConflictError,
    check_idempotency,
    clear_idempotency_reservation,
    normalize_idempotency_key,
    store_idempotency_response,
)


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str):
        return self._store.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self._store[key] = value.encode("utf-8")

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):  # noqa: ARG002
        if nx and key in self._store:
            return False
        self._store[key] = value.encode("utf-8")
        return True

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


def test_normalize_idempotency_key_validation() -> None:
    assert normalize_idempotency_key(None) is None
    assert normalize_idempotency_key(" " * 4) is None
    with pytest.raises(ValueError):
        normalize_idempotency_key("short")


def test_idempotency_replay_and_conflict(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr("app.services.idempotency_service.get_redis", lambda: fake)

    key = "0123456789abcdef"
    payload = {"route": "x", "value": 1}
    response = {"ok": True, "idempotency_replayed": False}

    first = check_idempotency(namespace="unit", idempotency_key=key, payload=payload)
    assert first.replayed is False
    assert first.response is None

    store_idempotency_response(
        namespace="unit",
        idempotency_key=key,
        payload=payload,
        response=response,
    )

    replay = check_idempotency(namespace="unit", idempotency_key=key, payload=payload)
    assert replay.replayed is True
    assert replay.response == response

    with pytest.raises(IdempotencyConflictError):
        check_idempotency(namespace="unit", idempotency_key=key, payload={"route": "x", "value": 2})


def test_clear_idempotency_reservation_unblocks_retries(monkeypatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr("app.services.idempotency_service.get_redis", lambda: fake)

    key = "abcdef0123456789"
    payload = {"route": "x", "value": 1}
    check_idempotency(namespace="unit", idempotency_key=key, payload=payload)
    with pytest.raises(IdempotencyConflictError):
        check_idempotency(namespace="unit", idempotency_key=key, payload=payload)

    clear_idempotency_reservation(namespace="unit", idempotency_key=key, payload=payload)
    replay = check_idempotency(namespace="unit", idempotency_key=key, payload=payload)
    assert replay.replayed is False
