from scripts.symbiote_lite_agent import (
    reset_session,
    session_state,
    extract_slots_from_text,
)

def setup_function():
    session_state.clear()
    session_state.update(reset_session())

def test_extract_iso_dates_and_granularity():
    text = "Analyze monthly trip frequency from 2022-01-01 to 2022-06-01"
    extract_slots_from_text(text)

    assert session_state["granularity"] == "monthly"
    assert session_state["start_date"].strftime("%Y-%m-%d") == "2022-01-01"
    assert session_state["end_date"].strftime("%Y-%m-%d") == "2022-06-01"

def test_extract_textual_months():
    text = "show trips from January to June 2022 by month"
    extract_slots_from_text(text)

    assert session_state["granularity"] == "monthly"
    assert session_state["start_date"].year == 2022
    assert session_state["end_date"].year == 2022

def test_extract_weekly_keyword():
    text = "weekly trip frequency in Feb 2022"
    extract_slots_from_text(text)

    assert session_state["granularity"] == "weekly"
