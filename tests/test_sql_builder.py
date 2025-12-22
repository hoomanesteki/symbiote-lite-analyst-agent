"""
Tests for the SQL builder module.
Covers SQL generation for all intent types.
"""
from datetime import datetime
import pytest

from symbiote_lite.sql.builder import build_sql, time_bucket


class TestTimeBucket:
    """Test time bucket SQL generation."""

    def test_daily_bucket(self):
        """Test daily time bucket."""
        expr, label = time_bucket("daily")
        assert "DATE(pickup_datetime)" in expr
        assert label == "day"

    def test_weekly_bucket(self):
        """Test weekly time bucket."""
        expr, label = time_bucket("weekly")
        assert "STRFTIME('%Y-%W', pickup_datetime)" in expr
        assert label == "week"

    def test_monthly_bucket(self):
        """Test monthly time bucket."""
        expr, label = time_bucket("monthly")
        assert "STRFTIME('%Y-%m', pickup_datetime)" in expr
        assert label == "month"


class TestBuildTripFrequencySQL:
    """Test trip_frequency SQL generation."""

    def test_build_daily(self):
        """Test daily trip frequency SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
        }
        sql = build_sql(state, "trip_frequency")
        
        assert "COUNT(*) AS trips" in sql
        assert "DATE(pickup_datetime) AS day" in sql
        assert "'2022-01-01'" in sql
        assert "'2022-02-01'" in sql
        assert "GROUP BY 1" in sql
        assert "ORDER BY 1" in sql

    def test_build_weekly(self):
        """Test weekly trip frequency SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "weekly",
        }
        sql = build_sql(state, "trip_frequency")
        
        assert "COUNT(*) AS trips" in sql
        assert "AS week" in sql

    def test_build_monthly(self):
        """Test monthly trip frequency SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 6, 1),
            "granularity": "monthly",
        }
        sql = build_sql(state, "trip_frequency")
        
        assert "COUNT(*) AS trips" in sql
        assert "AS month" in sql


class TestBuildFareTrendSQL:
    """Test fare_trend SQL generation."""

    def test_build_avg_fare(self):
        """Test average fare trend SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
            "metric": "avg",
        }
        sql = build_sql(state, "fare_trend")
        
        assert "AVG(fare_amount) AS value" in sql
        assert "GROUP BY 1" in sql

    def test_build_total_fare(self):
        """Test total fare trend SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "weekly",
            "metric": "total",
        }
        sql = build_sql(state, "fare_trend")
        
        assert "SUM(fare_amount) AS value" in sql


class TestBuildTipTrendSQL:
    """Test tip_trend SQL generation."""

    def test_build_avg_tip(self):
        """Test average tip trend SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
            "metric": "avg",
        }
        sql = build_sql(state, "tip_trend")
        
        assert "AVG(tip_amount) AS value" in sql

    def test_build_total_tip(self):
        """Test total tip trend SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "monthly",
            "metric": "total",
        }
        sql = build_sql(state, "tip_trend")
        
        assert "SUM(tip_amount) AS value" in sql


class TestBuildVendorInactivitySQL:
    """Test vendor_inactivity SQL generation."""

    def test_build_vendor_sql(self):
        """Test vendor inactivity SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
        }
        sql = build_sql(state, "vendor_inactivity")
        
        assert "vendor_id" in sql
        assert "COUNT(*) AS trips" in sql
        assert "GROUP BY vendor_id" in sql
        assert "ORDER BY trips ASC" in sql


class TestBuildSampleRowsSQL:
    """Test sample_rows SQL generation."""

    def test_build_sample_default_limit(self):
        """Test sample rows with default limit."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "limit": None,
        }
        sql = build_sql(state, "sample_rows")
        
        assert "LIMIT 100" in sql
        assert "pickup_datetime" in sql
        assert "fare_amount" in sql
        assert "tip_amount" in sql

    def test_build_sample_custom_limit(self):
        """Test sample rows with custom limit."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "limit": 50,
        }
        sql = build_sql(state, "sample_rows")
        
        assert "LIMIT 50" in sql

    def test_build_sample_limit_capped(self):
        """Test sample rows limit is capped at 1000."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "limit": 5000,
        }
        sql = build_sql(state, "sample_rows")
        
        assert "LIMIT 1000" in sql

    def test_build_sample_limit_minimum(self):
        """Test sample rows limit has minimum of 1."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "limit": 0,
        }
        sql = build_sql(state, "sample_rows")
        
        assert "LIMIT 1" in sql


class TestSQLSafety:
    """Test generated SQL is safe."""

    def test_sql_is_select_only(self):
        """Test all generated SQL starts with SELECT."""
        intents = ["trip_frequency", "fare_trend", "tip_trend", "vendor_inactivity", "sample_rows"]
        
        for intent in intents:
            state = {
                "start_date": datetime(2022, 1, 1),
                "end_date": datetime(2022, 2, 1),
                "granularity": "daily",
                "metric": "avg",
                "limit": 100,
            }
            sql = build_sql(state, intent)
            assert sql.strip().upper().startswith("SELECT"), f"Failed for {intent}"

    def test_dates_properly_quoted(self):
        """Test dates are properly quoted in SQL."""
        state = {
            "start_date": datetime(2022, 1, 1),
            "end_date": datetime(2022, 2, 1),
            "granularity": "daily",
        }
        sql = build_sql(state, "trip_frequency")
        
        # Dates should be quoted strings
        assert "'>= '2022-01-01'" in sql or ">= '2022-01-01'" in sql
