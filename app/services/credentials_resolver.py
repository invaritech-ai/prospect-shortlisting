"""Provider credential resolver: DB-first with env fallback.

Every integration client reads credentials through this module so that the
DB-backed settings store takes precedence over the static env-based
``settings.*`` values. If the DB value is missing (or the secret store is
disabled), we gracefully fall back to the env-based value, preserving the
legacy behavior.

Providers and fields
--------------------
- ``openrouter``: ``api_key``
- ``snov``: ``client_id``, ``client_secret``
- ``apollo``: ``api_key``
- ``zerobounce``: ``api_key``

Resolution flow
---------------
1. Open a short-lived :class:`Session` against the shared engine.
2. Ask :mod:`secret_store` for the decrypted secret.
3. If absent, fall back to ``settings.<env_field>``.
4. Trim whitespace and return the string. Empty string means "not set".

Source tracking
---------------
:func:`resolve_with_source` returns a ``(value, source)`` tuple where
``source`` is one of ``"db"``, ``"env"`` or ``""`` (missing in both).
"""
from __future__ import annotations

import logging
from typing import Literal

from sqlmodel import Session

from app.core.config import settings
from app.core.logging import log_event
from app.db.session import engine
from app.services import secret_store

logger = logging.getLogger(__name__)


CredentialSource = Literal["db", "env", ""]


_ENV_FALLBACKS: dict[tuple[str, str], str] = {
    ("openrouter", "api_key"): "openrouter_api_key",
    ("snov", "client_id"): "snov_client_id",
    ("snov", "client_secret"): "snov_client_secret",
    ("apollo", "api_key"): "apollo_api_key",
    ("zerobounce", "api_key"): "zerobounce_api_key",
}


def _env_value(provider: str, field_name: str) -> str:
    env_field = _ENV_FALLBACKS.get((provider, field_name))
    if not env_field:
        return ""
    raw = getattr(settings, env_field, "") or ""
    return str(raw).strip()


def resolve_env_fallback(provider: str, field_name: str) -> str:
    """Return the env-backed fallback value only, without consulting the DB."""
    return _env_value(provider, field_name)


def _db_value(provider: str, field_name: str) -> str:
    if not secret_store.is_available():
        return ""
    try:
        with Session(engine) as session:
            value = secret_store.get_secret(session, provider, field_name)
    except Exception as exc:  # noqa: BLE001
        log_event(
            logger,
            "credentials_resolver_db_error",
            provider=provider,
            field=field_name,
            error=str(exc),
        )
        return ""
    return (value or "").strip()


def resolve_with_source(provider: str, field_name: str) -> tuple[str, CredentialSource]:
    """Resolve a provider credential. Returns ``(value, source)``.

    ``source`` is ``"db"`` when the value came from the encrypted settings
    store, ``"env"`` when it came from the env-based config fallback, or
    ``""`` when neither source has the value.
    """
    db_val = _db_value(provider, field_name)
    if db_val:
        return db_val, "db"
    env_val = _env_value(provider, field_name)
    if env_val:
        return env_val, "env"
    return "", ""


def resolve(provider: str, field_name: str) -> str:
    """Convenience wrapper returning only the resolved value."""
    value, _ = resolve_with_source(provider, field_name)
    return value
