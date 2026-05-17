from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, event
from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel import Field, SQLModel

_MISSING = object()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_datetime_field(
    *,
    default: datetime | None | object = _MISSING,
    default_factory: Any = _MISSING,
    nullable: bool = False,
    index: bool = False,
) -> Any:
    field_kwargs: dict[str, Any] = {
        "sa_column": Column(DateTime(timezone=True), nullable=nullable, index=index),
    }
    if default_factory is not _MISSING:
        field_kwargs["default_factory"] = default_factory
    elif default is not _MISSING:
        field_kwargs["default"] = default
    return Field(**field_kwargs)


def coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_model_datetimes(target: Any) -> None:
    mapper = getattr(target, "__mapper__", None)
    if mapper is None:
        return
    for prop in mapper.column_attrs:
        value = getattr(target, prop.key, None)
        if isinstance(value, datetime):
            normalized = coerce_utc_datetime(value)
            if normalized != value:
                set_committed_value(target, prop.key, normalized)


@event.listens_for(SQLModel, "load", propagate=True)
def _normalize_loaded_model_datetimes(target: Any, _context: Any) -> None:
    _normalize_model_datetimes(target)


@event.listens_for(SQLModel, "refresh", propagate=True)
def _normalize_refreshed_model_datetimes(target: Any, _context: Any, _attrs: Any) -> None:
    _normalize_model_datetimes(target)
