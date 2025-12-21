import pytest
from scripts.symbiote_lite_agent import (
    validate_date,
    validate_range,
    normalize_granularity,
    normalize_metric,
)

def test_validate_date_valid():
    validate_date("2022-05-01")

def test_validate_date_invalid_year():
    with pytest.raises(ValueError):
        validate_date("2023-01-01")

def test_validate_range_ok():
    validate_range("2022-01-01", "2022-02-01")

def test_validate_range_bad():
    with pytest.raises(ValueError):
        validate_range("2022-03-01", "2022-02-01")

def test_normalize_granularity():
    assert normalize_granularity("weekly") == "weekly"
    assert normalize_granularity("day") == "daily"

def test_normalize_metric():
    assert normalize_metric("sum") == "total"
    assert normalize_metric("avg") == "avg"
