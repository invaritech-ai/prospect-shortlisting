from __future__ import annotations

from sqlmodel import Session

from app.services import secret_store


def test_resolve_with_source_prefers_db_over_env(monkeypatch, sqlite_engine, sqlite_session: Session) -> None:
    from app.services import credentials_resolver

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "unit-test-settings-key")
    monkeypatch.setattr("app.core.config.settings.openrouter_api_key", "env-openrouter-1111")
    monkeypatch.setattr(credentials_resolver, "engine", sqlite_engine)
    secret_store.reset_cipher_cache()

    secret_store.set_secret(
        sqlite_session,
        provider="openrouter",
        field_name="api_key",
        value="db-openrouter-9999",
    )

    value, source = credentials_resolver.resolve_with_source("openrouter", "api_key")

    assert value == "db-openrouter-9999"
    assert source == "db"


def test_resolve_with_source_falls_back_to_env_when_db_missing(monkeypatch, sqlite_engine) -> None:
    from app.services import credentials_resolver

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "unit-test-settings-key")
    monkeypatch.setattr("app.core.config.settings.apollo_api_key", "env-apollo-2222")
    monkeypatch.setattr(credentials_resolver, "engine", sqlite_engine)
    secret_store.reset_cipher_cache()

    value, source = credentials_resolver.resolve_with_source("apollo", "api_key")

    assert value == "env-apollo-2222"
    assert source == "env"


def test_resolve_with_source_uses_env_when_db_row_exists_but_store_is_unavailable(
    monkeypatch,
    sqlite_engine,
    sqlite_session: Session,
) -> None:
    from app.services import credentials_resolver

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "unit-test-settings-key")
    monkeypatch.setattr(credentials_resolver, "engine", sqlite_engine)
    secret_store.reset_cipher_cache()

    secret_store.set_secret(
        sqlite_session,
        provider="zerobounce",
        field_name="api_key",
        value="db-zerobounce-9999",
    )

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "")
    monkeypatch.setattr("app.core.config.settings.zerobounce_api_key", "env-zerobounce-1234")
    secret_store.reset_cipher_cache()

    value, source = credentials_resolver.resolve_with_source("zerobounce", "api_key")

    assert value == "env-zerobounce-1234"
    assert source == "env"
