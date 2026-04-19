from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.services.redis_client import get_redis

_IDEMPOTENCY_TTL_SEC = 24 * 60 * 60


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused with a different payload."""


class IdempotencyUnavailableError(RuntimeError):
    """Raised when idempotency is requested but backing store is unavailable."""


@dataclass
class ReplayResult:
    idempotency_key: str
    replayed: bool
    response: dict[str, Any] | None


def normalize_idempotency_key(raw: str | None) -> str | None:
    if raw is not None and not isinstance(raw, str):
        raw = getattr(raw, "default", None)
    key = (raw or "").strip()
    if not key:
        return None
    if len(key) < 16 or len(key) > 128:
        raise ValueError("X-Idempotency-Key must be 16-128 characters.")
    return key


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cache_key(*, namespace: str, key: str) -> str:
    return f"idempotency:{namespace}:{key}"


def check_idempotency(
    *,
    namespace: str,
    idempotency_key: str | None,
    payload: dict[str, Any],
) -> ReplayResult:
    if not idempotency_key:
        return ReplayResult(idempotency_key="", replayed=False, response=None)

    redis = get_redis()
    if redis is None:
        raise IdempotencyUnavailableError("Idempotency store unavailable; retry later.")

    cache_key = _cache_key(namespace=namespace, key=idempotency_key)
    incoming_hash = _payload_hash(payload)
    reservation = {
        "payload_hash": incoming_hash,
        "state": "in_progress",
    }
    reserved = redis.set(cache_key, json.dumps(reservation), ex=_IDEMPOTENCY_TTL_SEC, nx=True)
    if reserved:
        return ReplayResult(idempotency_key=idempotency_key, replayed=False, response=None)

    raw = redis.get(cache_key)
    if not raw:
        return ReplayResult(idempotency_key=idempotency_key, replayed=False, response=None)
    try:
        blob = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return ReplayResult(idempotency_key=idempotency_key, replayed=False, response=None)

    stored_hash = str(blob.get("payload_hash") or "")
    if stored_hash and stored_hash != incoming_hash:
        raise IdempotencyConflictError("Idempotency key already used with different payload.")

    if str(blob.get("state") or "") == "in_progress":
        raise IdempotencyConflictError("An identical request with this idempotency key is already in progress.")

    response = blob.get("response")
    if not isinstance(response, dict):
        return ReplayResult(idempotency_key=idempotency_key, replayed=False, response=None)

    return ReplayResult(idempotency_key=idempotency_key, replayed=True, response=response)


def store_idempotency_response(
    *,
    namespace: str,
    idempotency_key: str | None,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> None:
    if not idempotency_key:
        return
    redis = get_redis()
    if redis is None:
        return

    cache_key = _cache_key(namespace=namespace, key=idempotency_key)
    blob = {
        "payload_hash": _payload_hash(payload),
        "state": "done",
        "response": response,
    }
    redis.setex(cache_key, _IDEMPOTENCY_TTL_SEC, json.dumps(blob, default=str))


def clear_idempotency_reservation(
    *,
    namespace: str,
    idempotency_key: str | None,
    payload: dict[str, Any],
) -> None:
    if not idempotency_key:
        return
    redis = get_redis()
    if redis is None:
        return
    cache_key = _cache_key(namespace=namespace, key=idempotency_key)
    raw = redis.get(cache_key)
    if not raw:
        return
    try:
        blob = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return
    if str(blob.get("state") or "") != "in_progress":
        return
    if str(blob.get("payload_hash") or "") != _payload_hash(payload):
        return
    redis.delete(cache_key)
