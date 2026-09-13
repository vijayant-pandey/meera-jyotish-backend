from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "kundali_reports" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("kundali_reports")}
        if "user_id" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE kundali_reports ADD COLUMN user_id VARCHAR(32)"))
