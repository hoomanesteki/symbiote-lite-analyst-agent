from datetime import datetime

from symbiote_lite.slots import (
    reset_session,
    extract_slots_from_text,
    missing_slots,
    normalize_granularity,
    normalize_metric,
    validate_all_slots,
)

def test_reset_session():
    state = reset_session()
    assert state["intent"] is None
    assert state["_query_count"] == 0

def test_extract_slots_dates_and_granularity():
    state = reset_session()
    extract_slots_from_text(state, "show trips in january 2022 by week")
    assert state["granularity"] == "weekly"
    assert state["start_date"] == datetime(2022, 1, 1)

def test_missing_slots_trip_frequency():
    state = reset_session()
    state["intent"] = "trip_frequency"
    missing = missing_slots(state, "trip_frequency")
    assert "start_date" in missing
    assert "granularity" in missing

def test_normalize_granularity_typos():
    assert normalize_granularity("wekly") == "weekly"

def test_normalize_metric():
    assert normalize_metric("average") == "avg"

def test_validate_all_slots_success():
    state = reset_session()
    state.update({
        "intent": "trip_frequency",
        "start_date": datetime(2022, 1, 1),
        "end_date": datetime(2022, 2, 1),
        "granularity": "daily",
    })
    assert validate_all_slots(state) is True
