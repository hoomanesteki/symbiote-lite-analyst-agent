from datetime import datetime
import pytest

from symbiote_lite.dates import (
    extract_dates,
    validate_date,
    validate_range,
    recommend_granularity,
)

def test_extract_iso_dates():
    dates, invalid = extract_dates("from 2022-01-01 to 2022-02-01")
    assert len(dates) == 2
    assert invalid == []

def test_extract_month_name():
    dates, invalid = extract_dates("january 2022")
    assert dates[0] == datetime(2022, 1, 1)
    assert dates[1] == datetime(2022, 2, 1)

def test_invalid_date_format():
    with pytest.raises(ValueError):
        validate_date("2022-13-01")

def test_validate_range_order():
    with pytest.raises(ValueError):
        validate_range("2022-02-01", "2022-01-01")

def test_recommend_granularity():
    assert recommend_granularity(
        datetime(2022, 1, 1), datetime(2022, 1, 10)
    ) == "daily"
