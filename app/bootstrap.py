from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


# Columns added after a table first shipped. create_all() only creates missing
# tables, never missing columns, so each one is added here for databases that
# already exist. Kept additive and nullable/defaulted so it is safe to re-run.
ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("kundali_reports", "user_id", "VARCHAR(32)"),
    ("nav_items", "parent_label", "VARCHAR(120) DEFAULT ''"),
]


def ensure_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table, column, definition in ADDED_COLUMNS:
        if table not in tables:
            continue
        existing = {item["name"] for item in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
