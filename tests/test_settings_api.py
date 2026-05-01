from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from app.api.schemas.settings import IntegrationFieldUpdate, IntegrationProviderUpdateRequest
from app.models import IntegrationSecret
from app.services import secret_store


def _status_by_provider(response, provider: str):  # noqa: ANN001
    return next(item for item in response.providers if item.provider == provider)


def _field_status(provider_status, field: str):  # noqa: ANN001
    return next(item for item in provider_status.fields if item.field == field)


def test_list_integration_settings_reports_env_fallback(monkeypatch, db_session: Session) -> None:
    from app.api.routes.settings import list_integration_settings

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "")
    monkeypatch.setattr("app.core.config.settings.openrouter_api_key", "env-openrouter-1234")
    secret_store.reset_cipher_cache()

    response = list_integration_settings(session=db_session)

    assert response.store_available is False
    openrouter = _status_by_provider(response, "openrouter")
    api_key = _field_status(openrouter, "api_key")
    assert api_key.is_set is True
    assert api_key.source == "env"
    assert api_key.last4 == "1234"
    assert api_key.updated_at is None


def test_update_integration_provider_persists_encrypted_secret_over_env(
    monkeypatch,
    db_session: Session,
) -> None:
    from app.api.routes.settings import list_integration_settings, update_integration_provider

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "unit-test-settings-key")
    monkeypatch.setattr("app.core.config.settings.openrouter_api_key", "env-openrouter-1111")
    secret_store.reset_cipher_cache()

    status = update_integration_provider(
        "openrouter",
        payload=IntegrationProviderUpdateRequest(
            fields=[IntegrationFieldUpdate(field="api_key", value="db-openrouter-9999")]
        ),
        session=db_session,
    )

    api_key = _field_status(status, "api_key")
    assert api_key.is_set is True
    assert api_key.source == "db"
    assert api_key.last4 == "9999"
    assert api_key.updated_at is not None

    row = db_session.exec(
        select(IntegrationSecret)
        .where(IntegrationSecret.provider == "openrouter")
        .where(IntegrationSecret.field_name == "api_key")
    ).one()
    assert row.provider == "openrouter"
    assert row.field_name == "api_key"
    assert row.ciphertext != "db-openrouter-9999"
    assert "db-openrouter-9999" not in row.ciphertext

    listed = list_integration_settings(session=db_session)
    listed_api_key = _field_status(_status_by_provider(listed, "openrouter"), "api_key")
    assert listed_api_key.source == "db"
    assert listed_api_key.last4 == "9999"


def test_update_integration_provider_rejects_unknown_provider(db_session: Session) -> None:
    from app.api.routes.settings import update_integration_provider

    with pytest.raises(HTTPException) as excinfo:
        update_integration_provider(
            "unknown-provider",
            payload=IntegrationProviderUpdateRequest(fields=[]),
            session=db_session,
        )

    assert excinfo.value.status_code == 404


def test_test_integration_provider_returns_result_shape(monkeypatch, db_session: Session) -> None:
    from app.api.routes.settings import test_integration_provider

    with patch(
        "app.api.routes.settings._run_provider_health_check",
        return_value=(True, "env", "", "Credentials look valid."),
    ) as mock_health:
        response = test_integration_provider("apollo", session=db_session)

    mock_health.assert_called_once_with("apollo")
    assert response.provider == "apollo"
    assert response.ok is True
    assert response.source == "env"
    assert response.error_code == ""
    assert response.message == "Credentials look valid."


def test_update_snov_provider_rejects_mixed_source_pair(monkeypatch, db_session: Session) -> None:
    from app.api.routes.settings import update_integration_provider

    monkeypatch.setattr("app.core.config.settings.settings_encryption_key", "unit-test-settings-key")
    monkeypatch.setattr("app.core.config.settings.snov_client_id", "env-snov-client-id")
    monkeypatch.setattr("app.core.config.settings.snov_client_secret", "env-snov-client-secret")
    secret_store.reset_cipher_cache()

    with pytest.raises(HTTPException) as excinfo:
        update_integration_provider(
            "snov",
            payload=IntegrationProviderUpdateRequest(
                fields=[IntegrationFieldUpdate(field="client_id", value="db-snov-client-id")]
            ),
            session=db_session,
        )

    assert excinfo.value.status_code == 422
    assert "same source" in str(excinfo.value.detail).lower()
