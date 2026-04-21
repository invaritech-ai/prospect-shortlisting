"""Encrypted global secret store for integration credentials.

Stores provider API keys as Fernet-encrypted ciphertext keyed by
``(provider, field_name)``. The master key is read from
``settings.settings_encryption_key``.

Never returns plaintext via any masked/listing API — callers who need the
raw value must explicitly call :func:`get_secret` / :func:`get_plaintext`.

Design notes
------------
- Plaintext is only materialised in process memory when resolving a client
  credential; it is never logged.
- The store is a lazily-constructed singleton keyed off the master key so
  tests can rotate keys by clearing the cache via :func:`reset_cipher_cache`.
- When the master key is missing we return a disabled store — every read
  returns ``None`` and every write raises ``SecretStoreUnavailable``.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, select

from app.core.config import settings
from app.core.logging import log_event
from app.models import IntegrationSecret
from app.models.pipeline import utcnow

logger = logging.getLogger(__name__)


class SecretStoreUnavailable(RuntimeError):
    """Raised when a write is attempted without a master encryption key."""


@dataclass(frozen=True)
class SecretStatus:
    is_set: bool
    last4: str | None
    updated_at: datetime | None


_cipher_lock = Lock()
_cached_key: str = ""
_cached_cipher: Fernet | None = None


def _derive_fernet_key(raw_key: str) -> bytes:
    """Accept either a Fernet-compatible key (urlsafe-b64 32 bytes) or any
    passphrase which we hash into a Fernet-compatible key.
    """
    try:
        decoded = base64.urlsafe_b64decode(raw_key.encode("utf-8"))
        if len(decoded) == 32:
            return raw_key.encode("utf-8")
    except Exception:  # noqa: BLE001
        pass
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_cipher() -> Fernet | None:
    """Return a cached Fernet cipher, or ``None`` if the master key is unset."""
    global _cached_key, _cached_cipher  # noqa: PLW0603

    raw_key = (settings.settings_encryption_key or "").strip()
    if not raw_key:
        return None

    with _cipher_lock:
        if _cached_cipher is not None and _cached_key == raw_key:
            return _cached_cipher
        key = _derive_fernet_key(raw_key)
        _cached_cipher = Fernet(key)
        _cached_key = raw_key
        return _cached_cipher


def reset_cipher_cache() -> None:
    """Test hook: reset the cached Fernet instance."""
    global _cached_key, _cached_cipher  # noqa: PLW0603
    with _cipher_lock:
        _cached_key = ""
        _cached_cipher = None


def is_available() -> bool:
    """True when a master encryption key is configured."""
    return _get_cipher() is not None


def _encrypt(value: str) -> str:
    cipher = _get_cipher()
    if cipher is None:
        raise SecretStoreUnavailable(
            "Settings encryption key is not configured (PS_SETTINGS_ENCRYPTION_KEY)"
        )
    token = cipher.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def _decrypt(ciphertext: str) -> str | None:
    cipher = _get_cipher()
    if cipher is None:
        return None
    try:
        return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        log_event(
            logger,
            "secret_store_invalid_token",
            reason="decryption_failed_or_key_rotated",
        )
        return None


def _row(session: Session, provider: str, field_name: str) -> IntegrationSecret | None:
    return session.exec(
        select(IntegrationSecret)
        .where(IntegrationSecret.provider == provider)
        .where(IntegrationSecret.field_name == field_name)
    ).first()


def get_secret(session: Session, provider: str, field_name: str) -> str | None:
    """Return the decrypted secret value or ``None`` if missing/unavailable."""
    row = _row(session, provider, field_name)
    if row is None:
        return None
    plaintext = _decrypt(row.ciphertext)
    if plaintext is None:
        return None
    return plaintext or None


def get_status(session: Session, provider: str, field_name: str) -> SecretStatus:
    row = _row(session, provider, field_name)
    if row is None:
        return SecretStatus(is_set=False, last4=None, updated_at=None)
    return SecretStatus(is_set=True, last4=row.last4, updated_at=row.updated_at)


def set_secret(
    session: Session,
    *,
    provider: str,
    field_name: str,
    value: str,
    auto_commit: bool = True,
) -> SecretStatus:
    """Upsert an encrypted secret for the given provider/field.

    Empty string clears the stored secret (delete row).
    """
    value = (value or "").strip()
    row = _row(session, provider, field_name)

    if value == "":
        if row is not None:
            session.delete(row)
            if auto_commit:
                session.commit()
            else:
                session.flush()
        log_event(
            logger,
            "secret_store_cleared",
            provider=provider,
            field=field_name,
        )
        return SecretStatus(is_set=False, last4=None, updated_at=None)

    ciphertext = _encrypt(value)
    last4 = value[-4:] if len(value) >= 4 else None
    now = utcnow()

    if row is None:
        row = IntegrationSecret(
            provider=provider,
            field_name=field_name,
            ciphertext=ciphertext,
            last4=last4,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.ciphertext = ciphertext
        row.last4 = last4
        row.updated_at = now
        session.add(row)
    if auto_commit:
        session.commit()
        session.refresh(row)
    else:
        session.flush()

    log_event(
        logger,
        "secret_store_updated",
        provider=provider,
        field=field_name,
    )
    return SecretStatus(is_set=True, last4=row.last4, updated_at=row.updated_at)


def delete_secret(session: Session, *, provider: str, field_name: str) -> None:
    row = _row(session, provider, field_name)
    if row is None:
        return
    session.delete(row)
    session.commit()
    log_event(
        logger,
        "secret_store_cleared",
        provider=provider,
        field=field_name,
    )
