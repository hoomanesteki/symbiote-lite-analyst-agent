"""
Tests for the explain module.
Covers result explanation and follow-up suggestions.
"""
from datetime import datetime
import pytest
import pandas as pd

from symbiote_lite.explain import (
    estimate_rows,
    explain_sql,
    get_follow_up_suggestions,
    INTRO,
    HELP_TEXT,
)


class TestEstimateRows:
    """Test row estimation."""

    def test_estimate_rows_daily(self):
        """Test daily row estimation."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 1, 11),
            "granularity": "daily",
        }
        result = estimate_rows(state, "trip_frequency")
        assert result == "~10"

    def test_estimate_rows_weekly(self):
        """Test weekly row estimation."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "weekly",
        }
        result = estimate_rows(state, "trip_frequency")
        # 31 days / 7 ≈ 4 weeks
        assert "~4" in result or "~5" in result

    def test_estimate_rows_monthly(self):
        """Test monthly row estimation."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 6, 1),
            "granularity": "monthly",
        }
        result = estimate_rows(state, "trip_frequency")
        # 5 months
        assert "~5" in result or "~4" in result

    def test_estimate_rows_vendor(self):
        """Test vendor inactivity row estimation."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
        }
        result = estimate_rows(state, "vendor_inactivity")
        assert result == "~3-5"

    def test_estimate_rows_sample(self):
        """Test sample rows estimation."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "limit": 50,
        }
        result = estimate_rows(state, "sample_rows")
        assert result == "~50"

    def test_estimate_rows_sample_default(self):
        """Test sample rows estimation with default limit."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "limit": None,
        }
        result = estimate_rows(state, "sample_rows")
        assert result == "~100"

    def test_estimate_rows_no_granularity(self):
        """Test estimation without granularity."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": None,
        }
        result = estimate_rows(state, "trip_frequency")
        assert result == "unknown"


class TestExplainSQL:
    """Test SQL explanation generation."""

    def test_explain_trip_frequency(self):
        """Test trip frequency explanation."""
        state = {"metric": None}
        result = explain_sql(state, "trip_frequency")
        assert "trip" in result.lower()
        assert "count" in result.lower()

    def test_explain_vendor_inactivity(self):
        """Test vendor inactivity explanation."""
        state = {"metric": None}
        result = explain_sql(state, "vendor_inactivity")
        assert "vendor" in result.lower()

    def test_explain_fare_trend_avg(self):
        """Test fare trend average explanation."""
        state = {"metric": "avg"}
        result = explain_sql(state, "fare_trend")
        assert "average" in result.lower()
        assert "fare" in result.lower()

    def test_explain_fare_trend_total(self):
        """Test fare trend total explanation."""
        state = {"metric": "total"}
        result = explain_sql(state, "fare_trend")
        assert "total" in result.lower() or "sum" in result.lower()

    def test_explain_tip_trend(self):
        """Test tip trend explanation."""
        state = {"metric": "avg"}
        result = explain_sql(state, "tip_trend")
        assert "tip" in result.lower()

    def test_explain_sample_rows(self):
        """Test sample rows explanation."""
        state = {"metric": None}
        result = explain_sql(state, "sample_rows")
        assert "sample" in result.lower() or "raw" in result.lower()

    def test_explain_unknown_intent(self):
        """Test unknown intent explanation."""
        state = {"metric": None}
        result = explain_sql(state, "unknown_intent")
        assert len(result) > 0  # Should return something


class TestFollowUpSuggestions:
    """Test follow-up suggestion generation."""

    def test_suggestions_trip_frequency(self):
        """Test trip frequency suggestions."""
        suggestions = get_follow_up_suggestions("trip_frequency")
        assert len(suggestions) > 0
        # Should suggest related analyses
        suggestion_text = " ".join(suggestions).lower()
        assert "compare" in suggestion_text or "vendor" in suggestion_text or "fare" in suggestion_text

    def test_suggestions_vendor_inactivity(self):
        """Test vendor inactivity suggestions."""
        suggestions = get_follow_up_suggestions("vendor_inactivity")
        assert len(suggestions) > 0

    def test_suggestions_fare_trend(self):
        """Test fare trend suggestions."""
        suggestions = get_follow_up_suggestions("fare_trend")
        assert len(suggestions) > 0

    def test_suggestions_tip_trend(self):
        """Test tip trend suggestions."""
        suggestions = get_follow_up_suggestions("tip_trend")
        assert len(suggestions) > 0

    def test_suggestions_unknown(self):
        """Test unknown intent returns empty list."""
        suggestions = get_follow_up_suggestions("unknown")
        assert suggestions == []


class TestConstants:
    """Test module constants."""

    def test_intro_defined(self):
        """Test INTRO is defined and non-empty."""
        assert len(INTRO) > 0
        assert "Symbiote" in INTRO

    def test_help_text_defined(self):
        """Test HELP_TEXT is defined."""
        assert len(HELP_TEXT) > 0

    def test_intro_contains_examples(self):
        """Test INTRO contains usage examples."""
        assert "example" in INTRO.lower() or "2022" in INTRO

    def test_intro_mentions_constraints(self):
        """Test INTRO mentions data constraints."""
        assert "2022" in INTRO
