"""
Tests for the dates module.
Covers date parsing, validation, and extraction.
"""
from datetime import datetime
import pytest

from symbiote_lite.dates import (
    extract_dates,
    validate_date,
    validate_range,
    recommend_granularity,
    find_months_in_text,
    DATASET_YEAR,
    MIN_DATE,
    MAX_DATE,
)


class TestExtractDates:
    """Test date extraction from natural language."""

    def test_extract_iso_dates(self):
        """Test ISO format date extraction."""
        dates, invalid = extract_dates("from 2022-01-01 to 2022-02-01")
        assert len(dates) == 2
        assert dates[0] == datetime(2022, 1, 1)
        assert dates[1] == datetime(2022, 2, 1)
        assert invalid == []

    def test_extract_iso_dates_with_slashes(self):
        """Test ISO format with slashes."""
        dates, invalid = extract_dates("from 2022/03/15 to 2022/04/15")
        assert len(dates) == 2
        assert dates[0] == datetime(2022, 3, 15)

    def test_extract_month_name(self):
        """Test month name extraction."""
        dates, invalid = extract_dates("january 2022")
        assert dates[0] == datetime(2022, 1, 1)
        assert dates[1] == datetime(2022, 2, 1)

    def test_extract_month_name_misspelled(self):
        """Test common misspellings of months."""
        # Test February misspelling
        dates, _ = extract_dates("febuary 2022")
        assert dates[0] == datetime(2022, 2, 1)

        # Test September misspelling
        dates, _ = extract_dates("septmber 2022")
        assert dates[0] == datetime(2022, 9, 1)

    def test_extract_quarter(self):
        """Test quarter extraction."""
        dates, _ = extract_dates("Q2 2022")
        assert dates[0] == datetime(2022, 4, 1)
        assert dates[1] == datetime(2022, 7, 1)

    def test_extract_quarter_q1(self):
        """Test Q1 extraction."""
        dates, _ = extract_dates("q1 2022")
        assert dates[0] == datetime(2022, 1, 1)
        assert dates[1] == datetime(2022, 4, 1)

    def test_extract_quarter_q4(self):
        """Test Q4 extraction."""
        dates, _ = extract_dates("Q4 2022")
        assert dates[0] == datetime(2022, 10, 1)
        assert dates[1] == datetime(2023, 1, 1)

    def test_extract_season_summer(self):
        """Test summer season extraction."""
        dates, _ = extract_dates("summer 2022")
        assert dates[0] == datetime(2022, 6, 1)
        assert dates[1] == datetime(2022, 9, 1)

    def test_extract_season_winter(self):
        """Test winter season extraction."""
        dates, _ = extract_dates("winter 2022")
        assert dates[0] == datetime(2022, 1, 1)
        assert dates[1] == datetime(2022, 3, 1)

    def test_extract_whole_year(self):
        """Test whole year extraction."""
        dates, _ = extract_dates("whole year 2022")
        assert dates[0] == datetime(2022, 1, 1)
        assert dates[1] == datetime(2023, 1, 1)

    def test_extract_month_range(self):
        """Test extraction of month range."""
        dates, _ = extract_dates("from january to march 2022")
        assert dates[0] == datetime(2022, 1, 1)
        assert dates[1] == datetime(2022, 4, 1)

    def test_extract_invalid_dates(self):
        """Test invalid date detection."""
        dates, invalid = extract_dates("2022-13-45")
        assert len(invalid) > 0

    def test_extract_no_dates(self):
        """Test when no dates are found."""
        dates, invalid = extract_dates("show me some data")
        assert len(dates) == 0
        assert len(invalid) == 0


class TestValidateDate:
    """Test date validation."""

    def test_valid_date(self):
        """Test valid date passes."""
        validate_date("2022-06-15")  # Should not raise

    def test_invalid_date_format(self):
        """Test invalid format raises error."""
        with pytest.raises(ValueError):
            validate_date("2022-13-01")

    def test_date_wrong_year(self):
        """Test wrong year raises error."""
        with pytest.raises(ValueError):
            validate_date("2021-06-15")

    def test_date_at_boundary(self):
        """Test dates at boundaries."""
        validate_date("2022-01-01")  # Should pass
        validate_date("2022-12-31")  # Should pass


class TestValidateRange:
    """Test date range validation."""

    def test_valid_range(self):
        """Test valid range passes."""
        validate_range("2022-01-01", "2022-02-01")  # Should not raise

    def test_invalid_range_order(self):
        """Test reversed dates raises error."""
        with pytest.raises(ValueError):
            validate_range("2022-02-01", "2022-01-01")

    def test_same_date_range(self):
        """Test same start and end raises error."""
        with pytest.raises(ValueError):
            validate_range("2022-01-01", "2022-01-01")

    def test_range_outside_year(self):
        """Test dates outside 2022 raise error."""
        with pytest.raises(ValueError):
            validate_range("2021-01-01", "2022-02-01")


class TestRecommendGranularity:
    """Test granularity recommendation."""

    def test_short_range_daily(self):
        """Test short range recommends daily."""
        result = recommend_granularity(
            datetime(2022, 1, 1), datetime(2022, 1, 10)
        )
        assert result == "daily"

    def test_medium_range_weekly(self):
        """Test medium range recommends weekly."""
        result = recommend_granularity(
            datetime(2022, 1, 1), datetime(2022, 2, 15)
        )
        assert result == "weekly"

    def test_long_range_monthly(self):
        """Test long range recommends monthly."""
        result = recommend_granularity(
            datetime(2022, 1, 1), datetime(2022, 6, 1)
        )
        assert result == "monthly"


class TestFindMonthsInText:
    """Test month name finding."""

    def test_find_single_month(self):
        """Test finding single month."""
        months = find_months_in_text("january")
        assert 1 in months

    def test_find_multiple_months(self):
        """Test finding multiple months."""
        months = find_months_in_text("from january to march")
        assert 1 in months
        assert 3 in months

    def test_find_abbreviated_month(self):
        """Test abbreviated month names."""
        months = find_months_in_text("jan feb mar")
        assert 1 in months
        assert 2 in months
        assert 3 in months

    def test_no_months(self):
        """Test when no months found."""
        months = find_months_in_text("show me data")
        assert len(months) == 0


class TestConstants:
    """Test module constants."""

    def test_dataset_year(self):
        """Test dataset year constant."""
        assert DATASET_YEAR == 2022

    def test_min_max_dates(self):
        """Test min/max date constants."""
        assert MIN_DATE == datetime(2022, 1, 1)
        assert MAX_DATE == datetime(2023, 1, 1)
