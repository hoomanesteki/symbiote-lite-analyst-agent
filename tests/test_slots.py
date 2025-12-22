"""
Tests for the slots module.
Covers slot filling, validation, and normalization.
"""
from datetime import datetime
import pytest

from symbiote_lite.slots import (
    reset_session,
    extract_slots_from_text,
    missing_slots,
    normalize_granularity,
    normalize_metric,
    validate_all_slots,
    validate_dates_state,
    REQUIRED_SLOTS,
    SUPPORTED_INTENTS,
)


class TestResetSession:
    """Test session reset functionality."""

    def test_reset_session(self):
        """Test basic session reset."""
        state = reset_session()
        assert state["intent"] is None
        assert state["start_date"] is None
        assert state["end_date"] is None
        assert state["granularity"] is None
        assert state["metric"] is None
        assert state["_query_count"] == 0

    def test_reset_session_private_fields(self):
        """Test private fields are reset."""
        state = reset_session()
        assert state["_saw_invalid_iso_date"] is False
        assert state["_invalid_dates"] == []
        assert state["_last_sql"] is None
        assert state["_last_df"] is None


class TestExtractSlotsFromText:
    """Test slot extraction from text."""

    def test_extract_dates_and_granularity(self):
        """Test extracting dates and granularity."""
        state = reset_session()
        extract_slots_from_text(state, "show trips in january 2022 by week")
        assert state["granularity"] == "weekly"
        assert state["start_date"] == datetime(2022, 1, 1)
        assert state["end_date"] == datetime(2022, 2, 1)

    def test_extract_daily_granularity(self):
        """Test daily granularity extraction."""
        state = reset_session()
        extract_slots_from_text(state, "trips by day in march 2022")
        assert state["granularity"] == "daily"

    def test_extract_monthly_granularity(self):
        """Test monthly granularity extraction."""
        state = reset_session()
        extract_slots_from_text(state, "fares per month in 2022")
        assert state["granularity"] == "monthly"

    def test_extract_metric_total(self):
        """Test total metric extraction."""
        state = reset_session()
        extract_slots_from_text(state, "total fares in january 2022")
        assert state["metric"] == "total"

    def test_extract_metric_average(self):
        """Test average metric extraction."""
        state = reset_session()
        extract_slots_from_text(state, "average fares in january 2022")
        assert state["metric"] == "avg"

    def test_extract_iso_dates(self):
        """Test ISO date extraction."""
        state = reset_session()
        extract_slots_from_text(state, "from 2022-03-01 to 2022-04-01")
        assert state["start_date"] == datetime(2022, 3, 1)
        assert state["end_date"] == datetime(2022, 4, 1)

    def test_extract_swapped_dates_detected(self):
        """Test swapped dates are detected."""
        state = reset_session()
        extract_slots_from_text(state, "from 2022-06-01 to 2022-03-01")
        assert state["_dates_were_swapped"] is True

    def test_extract_invalid_dates_detected(self):
        """Test invalid dates are flagged."""
        state = reset_session()
        extract_slots_from_text(state, "from 2022-13-45 to 2022-02-01")
        assert state["_saw_invalid_iso_date"] is True
        assert len(state["_invalid_dates"]) > 0


class TestMissingSlots:
    """Test missing slot detection."""

    def test_missing_slots_trip_frequency(self):
        """Test missing slots for trip_frequency."""
        state = reset_session()
        state["intent"] = "trip_frequency"
        missing = missing_slots(state, "trip_frequency")
        assert "start_date" in missing
        assert "end_date" in missing
        assert "granularity" in missing

    def test_missing_slots_fare_trend(self):
        """Test missing slots for fare_trend."""
        state = reset_session()
        missing = missing_slots(state, "fare_trend")
        assert "start_date" in missing
        assert "metric" in missing
        assert "granularity" in missing

    def test_missing_slots_vendor(self):
        """Test missing slots for vendor_inactivity."""
        state = reset_session()
        missing = missing_slots(state, "vendor_inactivity")
        assert "start_date" in missing
        assert "end_date" in missing
        assert "granularity" not in missing  # Not required for vendor

    def test_no_missing_slots_when_filled(self):
        """Test no missing slots when all filled."""
        state = reset_session()
        state.update({
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
        })
        missing = missing_slots(state, "trip_frequency")
        assert len(missing) == 0


class TestNormalizeGranularity:
    """Test granularity normalization."""

    def test_normalize_standard_values(self):
        """Test standard granularity values."""
        assert normalize_granularity("daily") == "daily"
        assert normalize_granularity("weekly") == "weekly"
        assert normalize_granularity("monthly") == "monthly"

    def test_normalize_abbreviations(self):
        """Test abbreviated granularity values."""
        assert normalize_granularity("d") == "daily"
        assert normalize_granularity("w") == "weekly"
        assert normalize_granularity("m") == "monthly"

    def test_normalize_typos(self):
        """Test common typos."""
        assert normalize_granularity("wekly") == "weekly"
        assert normalize_granularity("dialy") == "daily"
        assert normalize_granularity("montly") == "monthly"

    def test_normalize_variations(self):
        """Test common variations."""
        assert normalize_granularity("day") == "daily"
        assert normalize_granularity("days") == "daily"
        assert normalize_granularity("week") == "weekly"
        assert normalize_granularity("weeks") == "weekly"
        assert normalize_granularity("month") == "monthly"
        assert normalize_granularity("months") == "monthly"

    def test_normalize_with_extra_text(self):
        """Test granularity with extra text."""
        assert normalize_granularity("daily aggregation") == "daily"
        assert normalize_granularity("weekly please") == "weekly"

    def test_normalize_invalid_raises(self):
        """Test invalid granularity raises error."""
        with pytest.raises(ValueError):
            normalize_granularity("yearly")
        with pytest.raises(ValueError):
            normalize_granularity("")
        with pytest.raises(ValueError):
            normalize_granularity("xyz")


class TestNormalizeMetric:
    """Test metric normalization."""

    def test_normalize_standard_values(self):
        """Test standard metric values."""
        assert normalize_metric("avg") == "avg"
        assert normalize_metric("total") == "total"

    def test_normalize_variations(self):
        """Test metric variations."""
        assert normalize_metric("average") == "avg"
        assert normalize_metric("mean") == "avg"
        assert normalize_metric("sum") == "total"

    def test_normalize_abbreviations(self):
        """Test metric abbreviations."""
        assert normalize_metric("a") == "avg"
        assert normalize_metric("t") == "total"
        assert normalize_metric("s") == "total"

    def test_normalize_with_extra_text(self):
        """Test metric with extra text."""
        assert normalize_metric("average please") == "avg"
        assert normalize_metric("total sum") == "total"

    def test_normalize_invalid_raises(self):
        """Test invalid metric raises error."""
        with pytest.raises(ValueError):
            normalize_metric("median")
        with pytest.raises(ValueError):
            normalize_metric("")


class TestValidateAllSlots:
    """Test full slot validation."""

    def test_validate_success_trip_frequency(self):
        """Test successful validation for trip_frequency."""
        state = reset_session()
        state.update({
            "intent": "trip_frequency",
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
        })
        assert validate_all_slots(state) is True

    def test_validate_success_fare_trend(self):
        """Test successful validation for fare_trend."""
        state = reset_session()
        state.update({
            "intent": "fare_trend",
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "weekly",
            "metric": "avg",
        })
        assert validate_all_slots(state) is True

    def test_validate_missing_granularity(self, capsys):
        """Test validation fails without granularity."""
        state = reset_session()
        state.update({
            "intent": "trip_frequency",
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": None,
        })
        result = validate_all_slots(state)
        assert result is False

    def test_validate_missing_metric(self, capsys):
        """Test validation fails without metric for fare_trend."""
        state = reset_session()
        state.update({
            "intent": "fare_trend",
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
            "metric": None,
        })
        result = validate_all_slots(state)
        assert result is False


class TestConstants:
    """Test module constants."""

    def test_required_slots_defined(self):
        """Test all intents have required slots defined."""
        for intent in SUPPORTED_INTENTS:
            assert intent in REQUIRED_SLOTS

    def test_supported_intents(self):
        """Test supported intents are defined."""
        expected = {"trip_frequency", "vendor_inactivity", "fare_trend", "tip_trend", "sample_rows"}
        assert SUPPORTED_INTENTS == expected
