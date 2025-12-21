import pytest
from scripts.symbiote_lite_agent import (
    safe_select_only,
    build_sql,
    reset_session,
    session_state,
)

def setup_function():
    session_state.clear()
    session_state.update(reset_session())
    session_state["start_date"] = "2022-01-01"
    session_state["end_date"] = "2022-02-01"
    session_state["granularity"] = "monthly"
    session_state["metric"] = "avg"

def test_safe_select_allows_select():
    sql = "SELECT * FROM taxi_trips"
    assert safe_select_only(sql).startswith("SELECT")

def test_safe_select_blocks_delete():
    with pytest.raises(ValueError):
        safe_select_only("DELETE FROM taxi_trips")

def test_build_trip_frequency_sql():
    session_state["intent"] = "trip_frequency"
    sql = build_sql("trip_frequency")
    assert "COUNT(*)" in sql
    assert "GROUP BY" in sql
