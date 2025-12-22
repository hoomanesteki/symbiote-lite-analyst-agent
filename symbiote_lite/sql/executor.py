from __future__ import annotations

import os
import sqlite3
from pathlib import Path
import pandas as pd

def _default_db_path() -> Path:
    # Allow override for Docker/CI
    env = os.getenv("SYMBIOTE_DB_PATH")
    if env:
        return Path(env).expanduser().resolve()
    # project_root/data/taxi_trips.sqlite (project_root = .../symbiote-lite/)
    return Path(__file__).resolve().parents[2] / "data" / "taxi_trips.sqlite"

def execute_sql_query(sql: str, db_path: Path | None = None) -> pd.DataFrame:
    """Execute a SELECT-only query against the configured SQLite DB and return a DataFrame."""
    path = (db_path or _default_db_path())
    if not path.exists():
        raise FileNotFoundError(
            f"SQLite DB not found at: {path}. "
            "Set SYMBIOTE_DB_PATH or place the DB at ./data/taxi_trips.sqlite"
        )
    with sqlite3.connect(str(path)) as conn:
        return pd.read_sql_query(sql, conn)
