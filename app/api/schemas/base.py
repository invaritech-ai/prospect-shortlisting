from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, model_validator


class UTCReadModel(BaseModel):
    """Base for API read schemas.

    SQLAlchemy returns naive datetimes from TIMESTAMP WITHOUT TIME ZONE columns.
    FastAPI serialises these without the '+00:00' offset, so browsers treat them
    as local time instead of UTC. This validator attaches UTC to any naive
    datetime field so the serialised output is always timezone-aware.
    """

    @model_validator(mode="after")
    def _ensure_utc(self) -> "UTCReadModel":
        for field_name in type(self).model_fields:
            value = getattr(self, field_name, None)
            if isinstance(value, datetime) and value.tzinfo is None:
                setattr(self, field_name, value.replace(tzinfo=timezone.utc))
        return self
