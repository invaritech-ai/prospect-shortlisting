from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.schemas.settings import (
    IntegrationFieldStatus,
    IntegrationProviderStatus,
    IntegrationProviderUpdateRequest,
    IntegrationsStatusResponse,
    IntegrationTestResponse,
)
from app.core.config import settings
from app.core.logging import log_event
from app.db.session import get_session
from app.services import credentials_resolver, secret_store
from app.services.apollo_client import (
    ERR_APOLLO_AUTH_FAILED,
    ERR_APOLLO_CREDENTIALS_MISSING,
    ERR_APOLLO_FAILED,
)
from app.services.llm_client import ERR_API_KEY_MISSING
from app.services.snov_client import (
    ERR_SNOV_AUTH_FAILED,
    ERR_SNOV_CREDENTIALS_MISSING,
    SnovClient,
    clear_cached_access_tokens,
)
from app.services.zerobounce_client import (
    ERR_ZEROBOUNCE_AUTH_FAILED,
    ERR_ZEROBOUNCE_FAILED,
    ERR_ZEROBOUNCE_KEY_MISSING,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/settings", tags=["settings"])

_PROVIDERS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "label": "OpenRouter",
        "description": "Primary LLM gateway used for scraping and decision prompts.",
        "fields": ["api_key"],
    },
    "snov": {
        "label": "Snov.io",
        "description": "Contact discovery provider using OAuth client credentials.",
        "fields": ["client_id", "client_secret"],
    },
    "apollo": {
        "label": "Apollo",
        "description": "Contact discovery and enrichment provider.",
        "fields": ["api_key"],
    },
    "zerobounce": {
        "label": "ZeroBounce",
        "description": "Email verification provider used in S4 validation.",
        "fields": ["api_key"],
    },
}


def _provider_config_or_404(provider: str) -> dict[str, Any]:
    config = _PROVIDERS.get(provider)
    if config is None:
        raise HTTPException(status_code=404, detail="Unknown integration provider.")
    return config


def _composite_source(provider: str, fields: list[str]) -> str:
    resolved = [credentials_resolver.resolve_with_source(provider, field) for field in fields]
    if len([value for value, _source in resolved if value]) != len(fields):
        return ""
    sources = {source for _value, source in resolved if source}
    if len(sources) == 1:
        return next(iter(sources))
    return ""


def _build_field_status(session: Session, provider: str, field_name: str) -> IntegrationFieldStatus:
    db_value = secret_store.get_secret(session, provider, field_name)
    if db_value:
        masked = secret_store.get_status(session, provider, field_name)
        return IntegrationFieldStatus(
            field=field_name,
            is_set=True,
            source="db",
            last4=masked.last4,
            updated_at=masked.updated_at,
        )
    env_value = credentials_resolver.resolve_env_fallback(provider, field_name)
    if env_value:
        last4 = env_value[-4:] if len(env_value) >= 4 else None
        return IntegrationFieldStatus(
            field=field_name,
            is_set=True,
            source="env",
            last4=last4,
            updated_at=None,
        )

    # If DB rows exist but the store is unavailable (missing/rotated master key),
    # surface masked metadata without claiming that runtime can actually use them.
    masked = secret_store.get_status(session, provider, field_name)
    if masked.is_set:
        return IntegrationFieldStatus(
            field=field_name,
            is_set=True,
            source="",
            last4=masked.last4,
            updated_at=masked.updated_at,
        )
    return IntegrationFieldStatus(field=field_name, is_set=False, source="", last4=None, updated_at=None)


def _build_provider_status(session: Session, provider: str) -> IntegrationProviderStatus:
    config = _provider_config_or_404(provider)
    return IntegrationProviderStatus(
        provider=provider,
        label=config["label"],
        description=config["description"],
        fields=[_build_field_status(session, provider, field_name) for field_name in config["fields"]],
    )


def _predicted_field_source(
    session: Session,
    *,
    provider: str,
    field_name: str,
    overrides: dict[str, str],
) -> tuple[bool, str]:
    if field_name in overrides:
        override_value = overrides[field_name].strip()
        if override_value:
            return True, "db"
        env_value = credentials_resolver.resolve_env_fallback(provider, field_name)
        return bool(env_value), ("env" if env_value else "")

    current = _build_field_status(session, provider, field_name)
    return current.is_set, current.source


def _ensure_provider_update_is_consistent(
    session: Session,
    *,
    provider: str,
    valid_fields: list[str],
    payload: IntegrationProviderUpdateRequest,
) -> None:
    if provider != "snov":
        return
    overrides = {field.field: field.value for field in payload.fields if field.field in valid_fields}
    predicted = [
        _predicted_field_source(
            session,
            provider=provider,
            field_name=field_name,
            overrides=overrides,
        )
        for field_name in valid_fields
    ]
    live_sources = {source for is_set, source in predicted if is_set and source}
    if len(live_sources) <= 1:
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=(
            "Snov client_id and client_secret must resolve from the same source. "
            "Save both DB values together or clear the stored DB-backed pair together."
        ),
    )


def _check_openrouter() -> tuple[bool, str, str, str]:
    api_key, source = credentials_resolver.resolve_with_source("openrouter", "api_key")
    if not api_key:
        return False, source, ERR_API_KEY_MISSING, "OpenRouter API key is missing."
    try:
        response = httpx.get(
            f"{settings.openrouter_base_url.rstrip('/')}/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        return False, source, "openrouter_test_failed", f"OpenRouter test request failed: {exc}"
    if response.status_code == 200:
        return True, source, "", "Credentials look valid."
    if response.status_code in {401, 403}:
        return False, source, "openrouter_auth_failed", "OpenRouter rejected the API key."
    if response.status_code == 429:
        return False, source, "openrouter_rate_limited", "OpenRouter rate-limited the test request."
    return False, source, "openrouter_test_failed", f"OpenRouter returned HTTP {response.status_code}."


def _check_snov() -> tuple[bool, str, str, str]:
    source = _composite_source("snov", ["client_id", "client_secret"])
    if not source:
        return (
            False,
            "",
            "snov_credentials_source_mismatch",
            "Snov client ID and client secret must resolve from the same source.",
        )
    client = SnovClient()
    token, err = client._get_access_token(force_refresh=True)  # noqa: SLF001 - internal auth path is the credential check.
    if token and not err:
        return True, source, "", "Credentials look valid."
    if err == ERR_SNOV_CREDENTIALS_MISSING:
        return False, source, err, "Snov credentials are missing."
    if err == ERR_SNOV_AUTH_FAILED:
        return False, source, err, "Snov rejected the credentials."
    return False, source, err or "snov_test_failed", "Snov credential test failed."


def _check_apollo() -> tuple[bool, str, str, str]:
    api_key, source = credentials_resolver.resolve_with_source("apollo", "api_key")
    if not api_key:
        return False, source, ERR_APOLLO_CREDENTIALS_MISSING, "Apollo API key is missing."
    try:
        response = httpx.get(
            "https://api.apollo.io/v1/auth/health",
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": api_key,
            },
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        return False, source, ERR_APOLLO_FAILED, f"Apollo test request failed: {exc}"
    if response.status_code in {401, 403}:
        return False, source, ERR_APOLLO_AUTH_FAILED, "Apollo rejected the API key."
    if response.status_code >= 400:
        return False, source, ERR_APOLLO_FAILED, f"Apollo returned HTTP {response.status_code}."
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = {}
    bool_values = [value for value in payload.values() if isinstance(value, bool)] if isinstance(payload, dict) else []
    if bool_values and not all(bool_values):
        return False, source, ERR_APOLLO_AUTH_FAILED, "Apollo reported an unhealthy auth response."
    return True, source, "", "Credentials look valid."


def _check_zerobounce() -> tuple[bool, str, str, str]:
    api_key, source = credentials_resolver.resolve_with_source("zerobounce", "api_key")
    if not api_key:
        return False, source, ERR_ZEROBOUNCE_KEY_MISSING, "ZeroBounce API key is missing."
    try:
        response = httpx.get(
            "https://api.zerobounce.net/v2/getcredits",
            params={"api_key": api_key},
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        return False, source, ERR_ZEROBOUNCE_FAILED, f"ZeroBounce test request failed: {exc}"
    if response.status_code in {401, 403}:
        return False, source, ERR_ZEROBOUNCE_AUTH_FAILED, "ZeroBounce rejected the API key."
    if response.status_code >= 400:
        return False, source, ERR_ZEROBOUNCE_FAILED, f"ZeroBounce returned HTTP {response.status_code}."
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        return False, source, ERR_ZEROBOUNCE_FAILED, f"ZeroBounce returned invalid JSON: {exc}"
    credits = payload.get("Credits") if isinstance(payload, dict) else None
    if credits == -1:
        return False, source, ERR_ZEROBOUNCE_AUTH_FAILED, "ZeroBounce rejected the API key."
    return True, source, "", "Credentials look valid."


def _run_provider_health_check(provider: str) -> tuple[bool, str, str, str]:
    _provider_config_or_404(provider)
    if provider == "openrouter":
        return _check_openrouter()
    if provider == "snov":
        return _check_snov()
    if provider == "apollo":
        return _check_apollo()
    if provider == "zerobounce":
        return _check_zerobounce()
    raise AssertionError("unreachable")


@router.get("/integrations", response_model=IntegrationsStatusResponse)
def list_integration_settings(session: Session = Depends(get_session)) -> IntegrationsStatusResponse:
    return IntegrationsStatusResponse(
        store_available=secret_store.is_available(),
        providers=[_build_provider_status(session, provider) for provider in _PROVIDERS],
    )


@router.put("/integrations/{provider}", response_model=IntegrationProviderStatus)
def update_integration_provider(
    provider: str,
    payload: IntegrationProviderUpdateRequest,
    session: Session = Depends(get_session),
) -> IntegrationProviderStatus:
    config = _provider_config_or_404(provider)
    valid_fields = set(config["fields"])

    for field in payload.fields:
        if field.field not in valid_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Field '{field.field}' is not valid for provider '{provider}'.",
            )

    has_non_empty_update = any((field.value or "").strip() for field in payload.fields)
    if has_non_empty_update and not secret_store.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Settings encryption is not configured. Set PS_SETTINGS_ENCRYPTION_KEY first.",
        )

    _ensure_provider_update_is_consistent(
        session,
        provider=provider,
        valid_fields=config["fields"],
        payload=payload,
    )

    try:
        for field in payload.fields:
            secret_store.set_secret(
                session,
                provider=provider,
                field_name=field.field,
                value=field.value,
                auto_commit=False,
            )
        if payload.fields:
            session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        raise

    if provider == "snov" and payload.fields:
        clear_cached_access_tokens()

    log_event(
        logger,
        "integration_settings_updated",
        provider=provider,
        updated_fields=[field.field for field in payload.fields],
    )
    return _build_provider_status(session, provider)


@router.post("/integrations/{provider}/test", response_model=IntegrationTestResponse)
def test_integration_provider(
    provider: str,
    session: Session = Depends(get_session),  # kept for route consistency / future auth context
) -> IntegrationTestResponse:
    _ = session
    ok, source, error_code, message = _run_provider_health_check(provider)
    log_event(
        logger,
        "integration_settings_tested",
        provider=provider,
        ok=ok,
        source=source or None,
        error_code=error_code or None,
    )
    return IntegrationTestResponse(
        provider=provider,
        ok=ok,
        source=source,
        error_code=error_code,
        message=message,
    )
