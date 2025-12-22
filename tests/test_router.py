"""
Tests for the router module.
Covers intent classification and routing.
"""
import pytest

from symbiote_lite.router import (
    heuristic_route,
    ask_router,
    semantic_rewrite,
    configure_model,
)


class TestHeuristicRoute:
    """Test heuristic routing without LLM."""

    def test_route_trip_frequency(self):
        """Test trip frequency intent detection."""
        r = heuristic_route("show trips in january 2022")
        assert r["intent"] == "trip_frequency"
        assert r["dataset_match"] is True

    def test_route_trip_frequency_variations(self):
        """Test various trip frequency phrasings."""
        queries = [
            "how many rides in april",
            "trip count for summer",
            "volume of trips in Q2",
            "busy periods in march",
            "activity in february 2022",
        ]
        for query in queries:
            r = heuristic_route(query)
            assert r["intent"] == "trip_frequency", f"Failed for: {query}"

    def test_route_fare_trend(self):
        """Test fare trend intent detection."""
        r = heuristic_route("average fares in february 2022")
        assert r["intent"] == "fare_trend"

    def test_route_fare_trend_variations(self):
        """Test various fare phrasings."""
        queries = [
            "price trends in january",
            "revenue in Q1",
            "money made in summer",
            "how expensive were fares",
            "cost analysis for march",
        ]
        for query in queries:
            r = heuristic_route(query)
            assert r["intent"] == "fare_trend", f"Failed for: {query}"

    def test_route_tip_trend(self):
        """Test tip trend intent detection."""
        r = heuristic_route("tips in january 2022")
        assert r["intent"] == "tip_trend"

    def test_route_tip_not_strip(self):
        """Test 'tip' is detected but not 'strip'."""
        r = heuristic_route("show tip trends")
        assert r["intent"] == "tip_trend"

        r = heuristic_route("strip the data")
        assert r["intent"] != "tip_trend"

    def test_route_vendor_inactivity(self):
        """Test vendor intent detection."""
        r = heuristic_route("which vendors were inactive")
        assert r["intent"] == "vendor_inactivity"

    def test_route_sample_rows(self):
        """Test sample rows intent detection."""
        queries = [
            "show me a sample of rows",
            "sample 100 records",
            "limit to 50 rows",
        ]
        for query in queries:
            r = heuristic_route(query)
            assert r["intent"] == "sample_rows", f"Failed for: {query}"

    def test_route_out_of_scope_churn(self):
        """Test out of scope detection - churn."""
        r = heuristic_route("customer churn in 2021")
        assert r["dataset_match"] is False

    def test_route_out_of_scope_wrong_year(self):
        """Test out of scope detection - wrong year."""
        r = heuristic_route("trips in 2019")
        assert r["dataset_match"] is False

    def test_route_out_of_scope_cohort(self):
        """Test out of scope detection - cohort."""
        r = heuristic_route("cohort analysis")
        assert r["dataset_match"] is False

    def test_route_help_request(self):
        """Test help request detection."""
        queries = [
            "help",
            "what can i ask",
            "what can i do",
            "who are you",
        ]
        for query in queries:
            r = heuristic_route(query)
            assert r["intent"] == "unknown", f"Failed for: {query}"
            assert r["dataset_match"] is True

    def test_route_unknown_intent(self):
        """Test unknown intent."""
        r = heuristic_route("random gibberish xyz")
        assert r["intent"] == "unknown"


class TestAskRouter:
    """Test the ask_router function."""

    def test_ask_router_no_model(self):
        """Test router without LLM model."""
        r = ask_router(None, "show trips in january 2022")
        assert r["intent"] == "trip_frequency"

    def test_ask_router_fallback(self):
        """Test router falls back to heuristic."""
        r = ask_router(None, "fare analysis in Q2")
        assert r["intent"] == "fare_trend"


class TestSemanticRewrite:
    """Test semantic rewrite function."""

    def test_semantic_rewrite_no_model(self):
        """Test rewrite without LLM model."""
        r = semantic_rewrite(None, "show trips in january")
        assert r["rewritten"] == "show trips in january"
        assert r["intent_hint"] == "trip_frequency"

    def test_semantic_rewrite_preserves_query(self):
        """Test rewrite preserves original query when no model."""
        original = "average fares in summer 2022"
        r = semantic_rewrite(None, original)
        assert r["rewritten"] == original


class TestConfigureModel:
    """Test model configuration."""

    def test_configure_model_no_api_key(self, monkeypatch):
        """Test configure_model without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        model = configure_model()
        assert model is None

    def test_configure_model_with_empty_key(self, monkeypatch):
        """Test configure_model with empty API key."""
        monkeypatch.setenv("OPENAI_API_KEY", "")
        model = configure_model()
        assert model is None
