import pytest
from scripts.bq_tool import run_bigquery


def test_run_bigquery_rejects_empty_sql():
    """
    run_bigquery should fail fast when given empty SQL.
    This test does NOT call BigQuery.
    """
    with pytest.raises(ValueError):
        run_bigquery("")


def test_run_bigquery_rejects_non_string_sql():
    """
    run_bigquery should reject non-string inputs.
    """
    with pytest.raises(ValueError):
        run_bigquery(None)
