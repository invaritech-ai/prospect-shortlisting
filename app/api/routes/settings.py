from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.schemas.settings import (
    IntegrationFieldStatus,
    IntegrationHealthItem,
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

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    # Step 1: auth health (confirms key is accepted)
    try:
        auth_resp = httpx.get(
            "https://api.apollo.io/v1/auth/health",
            headers=headers,
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        return False, source, ERR_APOLLO_FAILED, f"Apollo test request failed: {exc}"
    if auth_resp.status_code in {401, 403}:
        return False, source, ERR_APOLLO_AUTH_FAILED, "Apollo rejected the API key."
    if auth_resp.status_code >= 400:
        return False, source, ERR_APOLLO_FAILED, f"Apollo returned HTTP {auth_resp.status_code}."

    # Step 2: probe enrichment permission via /people/match with an empty body.
    # A 200 (even with no match) means the plan allows enrichment.
    # A 403 means the plan does not include enrichment — S4 reveal will fail.
    try:
        enrich_resp = httpx.post(
            "https://api.apollo.io/api/v1/people/match",
            headers=headers,
            params={"reveal_personal_emails": "false"},
            json={},
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        return False, source, ERR_APOLLO_FAILED, f"Apollo enrichment probe failed: {exc}"
    if enrich_resp.status_code == 403:
        return False, source, ERR_APOLLO_AUTH_FAILED, (
            "Apollo key is valid for search but lacks enrichment permission "
            "(people/match returned 403). S4 email reveal will not work. "
            "Upgrade to an Apollo plan that includes enrichment credits."
        )
    if enrich_resp.status_code in {401}:
        return False, source, ERR_APOLLO_AUTH_FAILED, "Apollo rejected the API key on enrichment probe."

    return True, source, "", "Credentials look valid (auth + enrichment permission confirmed)."


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


def _health_openrouter() -> IntegrationHealthItem:
    api_key, _ = credentials_resolver.resolve_with_source("openrouter", "api_key")
    if not api_key:
        return IntegrationHealthItem(provider="openrouter", label="OpenRouter", connected=False,
                                     error_code=ERR_API_KEY_MISSING, message="API key not configured.")
    base = settings.openrouter_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": settings.openrouter_site_url,
        "X-Title": settings.openrouter_app_name,
    }
    try:
        # Verify key is valid first
        auth_resp = httpx.get(f"{base}/auth/key", headers=headers, timeout=10.0)
        if auth_resp.status_code in {401, 403}:
            return IntegrationHealthItem(provider="openrouter", label="OpenRouter", connected=False,
                                         error_code="openrouter_auth_failed", message="API key rejected.")
        if not auth_resp.is_success:
            return IntegrationHealthItem(provider="openrouter", label="OpenRouter", connected=False,
                                         error_code="openrouter_test_failed", message=f"HTTP {auth_resp.status_code}")

        # Fetch available credits: total_credits - total_usage
        credits: float | None = None
        try:
            credits_resp = httpx.get(f"{base}/credits", headers=headers, timeout=10.0)
            if credits_resp.is_success:
                cdata = credits_resp.json().get("data", {})
                total = cdata.get("total_credits")
                used = cdata.get("total_usage")
                if total is not None and used is not None:
                    credits = round(float(total) - float(used), 4)
        except Exception:  # noqa: BLE001
            pass

        return IntegrationHealthItem(provider="openrouter", label="OpenRouter", connected=True,
                                     credits_remaining=credits)
    except Exception as exc:  # noqa: BLE001
        return IntegrationHealthItem(provider="openrouter", label="OpenRouter", connected=False,
                                     error_code="openrouter_test_failed", message=str(exc))


def _health_snov() -> IntegrationHealthItem:
    ok, _, error_code, message = _check_snov()
    if not ok:
        return IntegrationHealthItem(provider="snov", label="Snov.io", connected=False,
                                     error_code=error_code, message=message)
    try:
        credits, _ = SnovClient().get_balance()
    except Exception:  # noqa: BLE001
        credits = None
    return IntegrationHealthItem(provider="snov", label="Snov.io", connected=True,
                                 credits_remaining=float(credits) if credits is not None else None)


def _health_apollo() -> IntegrationHealthItem:
    ok, _, error_code, message = _check_apollo()
    return IntegrationHealthItem(provider="apollo", label="Apollo", connected=ok,
                                 error_code=error_code if not ok else "",
                                 message=message if not ok else "")


def _health_zerobounce() -> IntegrationHealthItem:
    api_key, _ = credentials_resolver.resolve_with_source("zerobounce", "api_key")
    if not api_key:
        return IntegrationHealthItem(provider="zerobounce", label="ZeroBounce", connected=False,
                                     error_code=ERR_ZEROBOUNCE_KEY_MISSING, message="API key not configured.")
    try:
        resp = httpx.get("https://api.zerobounce.net/v2/getcredits",
                         params={"api_key": api_key}, timeout=10.0)
        if resp.status_code in {401, 403}:
            return IntegrationHealthItem(provider="zerobounce", label="ZeroBounce", connected=False,
                                         error_code=ERR_ZEROBOUNCE_AUTH_FAILED, message="API key rejected.")
        if not resp.is_success:
            return IntegrationHealthItem(provider="zerobounce", label="ZeroBounce", connected=False,
                                         error_code=ERR_ZEROBOUNCE_FAILED, message=f"HTTP {resp.status_code}")
        payload = resp.json()
        raw_credits = payload.get("Credits") if isinstance(payload, dict) else None
        if raw_credits == -1:
            return IntegrationHealthItem(provider="zerobounce", label="ZeroBounce", connected=False,
                                         error_code=ERR_ZEROBOUNCE_AUTH_FAILED, message="API key rejected.")
        credits = float(raw_credits) if raw_credits is not None else None
        return IntegrationHealthItem(provider="zerobounce", label="ZeroBounce", connected=True,
                                     credits_remaining=credits)
    except Exception as exc:  # noqa: BLE001
        return IntegrationHealthItem(provider="zerobounce", label="ZeroBounce", connected=False,
                                     error_code=ERR_ZEROBOUNCE_FAILED, message=str(exc))


@router.get("/integrations/health", response_model=list[IntegrationHealthItem])
def get_integrations_health() -> list[IntegrationHealthItem]:
    """Parallel connectivity + credits check for all four providers."""
    checkers = {
        "openrouter": _health_openrouter,
        "snov": _health_snov,
        "apollo": _health_apollo,
        "zerobounce": _health_zerobounce,
    }
    results: dict[str, IntegrationHealthItem] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn): key for key, fn in checkers.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[key] = IntegrationHealthItem(
                    provider=key, label=_PROVIDERS[key]["label"],
                    connected=False, error_code="health_check_failed", message=str(exc),
                )
    return [results[k] for k in ("openrouter", "snov", "apollo", "zerobounce")]


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
