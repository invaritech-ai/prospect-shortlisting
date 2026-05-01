from __future__ import annotations

from sqlalchemy import DateTime
from sqlmodel import SQLModel



def test_timestamp_columns_use_timezone_aware_datetimes() -> None:
    columns = []
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                columns.append((table.name, column.name, column.type.timezone))

    assert columns, "expected at least one datetime column"
    assert all(timezone is True for _, _, timezone in columns)
