from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .dates import extract_dates, validate_date, validate_range, recommend_granularity, ISO_DATE_RE

REQUIRED_SLOTS = {
    "trip_frequency": ["start_date", "end_date", "granularity"],
    "vendor_inactivity": ["start_date", "end_date"],
    "fare_trend": ["start_date", "end_date", "granularity", "metric"],
    "tip_trend": ["start_date", "end_date", "granularity", "metric"],
    "sample_rows": ["start_date", "end_date"],
}
SUPPORTED_INTENTS = set(REQUIRED_SLOTS)

def reset_session() -> Dict[str, Any]:
    return {
        "intent": None,
        "start_date": None,
        "end_date": None,
        "granularity": None,
        "metric": None,
        "limit": None,
        "_saw_invalid_iso_date": False,
        "_invalid_dates": [],
        "_last_query_context": None,
        "_last_suggestions": [],
        "_query_count": 0,
        "_last_sql": None,
        "_last_df": None,
        "_last_df_rows": 0,
        "_last_user_question": None,
        "_postprocess": None,
        "_dates_were_swapped": False,
        "_swapped_from": None,
        "_swapped_to": None,
    }

def missing_slots(state: Dict[str, Any], intent: str) -> List[str]:
    req = REQUIRED_SLOTS.get(intent, [])
    return [k for k in req if state.get(k) is None]

def normalize_granularity(value: str) -> str:
    v = (value or "").strip().lower()
    if not v:
        raise ValueError("Choose one: daily, weekly, monthly.")
    token = v.split()[0]
    if token in ("dialy", "daliy", "dailly"):
        token = "daily"
    if token in ("wekly", "weekely", "weekley"):
        token = "weekly"
    if token in ("montly", "monthy", "monthyl"):
        token = "monthly"
    if token in ("d", "day", "days", "daily"):
        return "daily"
    if token in ("w", "week", "weeks", "weekly"):
        return "weekly"
    if token in ("m", "month", "months", "monthly"):
        return "monthly"
    if token.startswith("dai") or token.startswith("day"):
        return "daily"
    if token.startswith("wee") or token.startswith("wk"):
        return "weekly"
    if token.startswith("mon") or token.startswith("mth"):
        return "monthly"
    raise ValueError("Choose one: daily, weekly, monthly.")

def normalize_metric(value: str) -> str:
    v = (value or "").strip().lower()
    parts = v.split()
    if not parts:
        raise ValueError("Choose one: avg, total.")
    v = parts[0]
    if v in ("total", "sum", "t", "s"):
        return "total"
    if v in ("avg", "average", "mean", "a"):
        return "avg"
    raise ValueError("Choose one: avg, total.")

def extract_slots_from_text(state: Dict[str, Any], user_input: str) -> None:
    dates, invalid_dates = extract_dates(user_input)
    if invalid_dates:
        state["_saw_invalid_iso_date"] = True
        state["_invalid_dates"] = invalid_dates

    # swap notice (only for explicit ISO dates)
    try:
        ordered = re.findall(r"\b2022-\d{2}-\d{2}\b", user_input)
        if len(ordered) >= 2:
            d0 = datetime.strptime(ordered[0], "%Y-%m-%d")
            d1 = datetime.strptime(ordered[1], "%Y-%m-%d")
            if d0 > d1:
                state["_dates_were_swapped"] = True
                state["_swapped_from"] = ordered[0]
                state["_swapped_to"] = ordered[1]
    except Exception:
        pass

    if len(dates) >= 1 and state.get("start_date") is None:
        state["start_date"] = dates[0]
    if len(dates) >= 2 and state.get("end_date") is None:
        state["end_date"] = dates[1]

    t = user_input.lower()
    if state.get("granularity") is None:
        if any(w in t for w in ["monthly", "by month", "per month"]):
            state["granularity"] = "monthly"
        elif any(w in t for w in ["weekly", "by week", "per week"]):
            state["granularity"] = "weekly"
        elif any(w in t for w in ["daily", "by day", "per day"]):
            state["granularity"] = "daily"

    if state.get("metric") is None:
        if any(w in t for w in ["total", "sum", "overall"]):
            state["metric"] = "total"
        elif any(w in t for w in ["avg", "average", "mean", "typical"]):
            state["metric"] = "avg"

def validate_dates_state(state: Dict[str, Any]) -> None:
    sd = state["start_date"].strftime("%Y-%m-%d")
    ed = state["end_date"].strftime("%Y-%m-%d")
    validate_range(sd, ed)

def validate_all_slots(state: Dict[str, Any]) -> bool:
    try:
        validate_dates_state(state)
        intent = state["intent"]
        if intent in ["trip_frequency", "fare_trend", "tip_trend"]:
            if not state.get("granularity"):
                print("⚠️  Internal error: missing granularity")
                return False
        if intent in ["fare_trend", "tip_trend"]:
            if not state.get("metric"):
                print("⚠️  Internal error: missing metric")
                return False
        return True
    except Exception as e:
        print(f"⚠️  Validation failed: {e}")
        return False
