import pytest

from symbiote_lite.sql.safety import detect_sql_injection, safe_select_only


def test_detect_sql_injection_true_cases():
    # Quoted / structured injection attempts
    assert detect_sql_injection("' OR '1'='1") is True
    assert detect_sql_injection("UNION SELECT * FROM users") is True
    assert detect_sql_injection("'; DROP TABLE taxi_trips; --") is True


def test_detect_sql_injection_false_cases():
    # Plain text or non-exploitable in this architecture
    assert detect_sql_injection("1 OR 1=1") is False
    assert detect_sql_injection("drop table taxi_trips;") is False
    assert detect_sql_injection("show trips in january 2022") is False


def test_safe_select_only_blocks_destructive_sql():
    with pytest.raises(ValueError):
        safe_select_only("DROP TABLE taxi_trips;")


def test_safe_select_only_allows_select():
    sql = "SELECT * FROM taxi_trips;"
    assert safe_select_only(sql) == sql
