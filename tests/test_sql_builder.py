from datetime import datetime

from symbiote_lite.sql.builder import build_sql

def test_build_trip_frequency_sql():
    state = {
        "start_date": datetime(2022, 1, 1),
        "end_date": datetime(2022, 2, 1),
        "granularity": "daily",
    }
    sql = build_sql(state, "trip_frequency")
    assert "COUNT(*) AS trips" in sql
    assert "DATE(pickup_datetime)" in sql

def test_build_sample_rows_sql():
    state = {
        "start_date": datetime(2022, 1, 1),
        "end_date": datetime(2022, 2, 1),
        "limit": 50,
    }
    sql = build_sql(state, "sample_rows")
    assert "LIMIT 50" in sql
