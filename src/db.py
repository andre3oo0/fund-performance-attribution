"""SQLite warehouse: connection and schema, rebuilt from the landed files whenever needed."""

import re
import sqlite3
from pathlib import Path

from src import config

SCHEMA = config.SQL_DIR / "schema.sql"


class StaleWarehouse(RuntimeError):
    pass


def schema_version() -> int:
    return int(re.search(r"PRAGMA user_version = (\d+)", SCHEMA.read_text(encoding="utf-8")).group(1))


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def apply_schema(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    has_tables = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
    if has_tables and current != schema_version():
        raise StaleWarehouse(f"Warehouse is v{current}, code expects v{schema_version()}: run python -m src.rebuild")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def run_sql(conn: sqlite3.Connection, name: str) -> None:
    conn.executescript((config.SQL_DIR / name).read_text(encoding="utf-8"))
