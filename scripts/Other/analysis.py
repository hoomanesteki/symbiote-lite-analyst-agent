import sqlite3
import pandas as pd
from pathlib import Path

# Absolute path to database
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "taxi.db"


def execute_sql_query(sql: str) -> pd.DataFrame:
    """
    Execute READ-ONLY SQL against the SQLite database.
    Only SELECT statements are allowed.
    """

    sql_clean = sql.strip().lower()

    # 🚨 Safety guard: block dangerous queries
    if not sql_clean.startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")

    conn = sqlite3.connect(DB_PATH)

    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        conn.close()

    return df
