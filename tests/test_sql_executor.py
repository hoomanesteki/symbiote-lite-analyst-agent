import pytest
from pathlib import Path

from symbiote_lite.sql.executor import execute_sql_query

def test_executor_missing_db(tmp_path):
    fake_db = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError):
        execute_sql_query("SELECT 1;", db_path=fake_db)
