from datetime import datetime
import pandas as pd

from symbiote_lite.explain import estimate_rows

def test_estimate_rows_daily():
    state = {
        "start_date": datetime(2022, 1, 1),
        "end_date": datetime(2022, 1, 11),
        "granularity": "daily",
    }
    assert estimate_rows(state, "trip_frequency") == "~10"
