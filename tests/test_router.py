from symbiote_lite.router import heuristic_route

def test_route_trip_frequency():
    r = heuristic_route("show trips in january 2022")
    assert r["intent"] == "trip_frequency"
    assert r["dataset_match"] is True

def test_route_fare_trend():
    r = heuristic_route("average fares in february 2022")
    assert r["intent"] == "fare_trend"

def test_route_out_of_scope():
    r = heuristic_route("customer churn in 2021")
    assert r["dataset_match"] is False
