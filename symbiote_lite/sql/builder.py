from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Tuple

def _date_to_str(d: Any) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        # Expected YYYY-MM-DD
        return datetime.strptime(d, "%Y-%m-%d").strftime("%Y-%m-%d")
    raise TypeError("start_date/end_date must be datetime or YYYY-MM-DD string")

def time_bucket(granularity: str) -> Tuple[str, str]:
    if granularity == "daily":
        return "DATE(pickup_datetime)", "day"
    if granularity == "weekly":
        return "STRFTIME('%Y-%W', pickup_datetime)", "week"
    return "STRFTIME('%Y-%m', pickup_datetime)", "month"

def build_sql(state: dict, intent: str) -> str:
    sd = _date_to_str(state["start_date"])
    ed = _date_to_str(state["end_date"])

    if intent == "trip_frequency":
        expr, label = time_bucket(state["granularity"])
        return f"""SELECT {expr} AS {label}, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY 1
ORDER BY 1;"""

    if intent == "sample_rows":
        limit = int(state.get("limit") or 100)
        limit = max(1, min(limit, 1000))
        return f"""SELECT pickup_datetime, dropoff_datetime, vendor_id, fare_amount, tip_amount, total_amount
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
ORDER BY pickup_datetime
LIMIT {limit};"""

    if intent == "vendor_inactivity":
        return f"""SELECT vendor_id, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY vendor_id
ORDER BY trips ASC;"""

    col = "fare_amount" if intent == "fare_trend" else "tip_amount"
    if intent == "fare_trend":
        pp = state.get("_postprocess") or {}
        if pp.get("type") == "best_day" and pp.get("mode") == "min_total_amount":
            col = "total_amount"

    agg = "SUM" if state["metric"] == "total" else "AVG"
    expr, label = time_bucket(state["granularity"])
    return f"""SELECT {expr} AS {label}, {agg}({col}) AS value
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY 1
ORDER BY 1;"""
