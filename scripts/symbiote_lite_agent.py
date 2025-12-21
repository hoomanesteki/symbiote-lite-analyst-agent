from __future__ import annotations
"""
Symbiote Lite — Human-in-the-Loop Analyst Agent (Gemini router + deterministic slots + safe SQL)

This file is written to satisfy BOTH:
1) your pytest suite expectations
2) real CLI robustness (no quota crash, validates dates, good prompts)

Key: tests expect:
- reset_session() returns dict
- session_state is a dict
- MODEL exists at module level (monkeypatched in test_router)
- ask_gemini_router parses JSON from MODEL.generate_content().text
- validate_range accepts strings
- normalize_metric("avg") -> "avg"
"""

# =============================================================================
# Environment
# =============================================================================
from pathlib import Path
import os
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # tests may not need dotenv

ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

# =============================================================================
# Third-party (Gemini) — optional in runtime, but tests monkeypatch MODEL anyway
# =============================================================================
try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None  # allow tests to run without google libs


# Package-relative import (your project uses this)
from .analysis import execute_sql_query


# =============================================================================
# Dataset constraints
# =============================================================================
DATASET_YEAR = 2022
MIN_DATE = datetime(2022, 1, 1)
MAX_DATE = datetime(2023, 1, 1)  # exclusive


# =============================================================================
# Session state
# =============================================================================
def reset_session() -> Dict[str, Any]:
    # IMPORTANT: tests call session_state.update(reset_session())
    return {
        "intent": None,
        "start_date": None,     # datetime OR string "YYYY-MM-DD"
        "end_date": None,       # datetime OR string "YYYY-MM-DD" (exclusive)
        "granularity": None,    # daily / weekly / monthly
        "metric": None,         # avg / total
    }


session_state: Dict[str, Any] = reset_session()


# =============================================================================
# Supported intents
# =============================================================================
REQUIRED_SLOTS = {
    "trip_frequency": ["start_date", "end_date", "granularity"],
    "vendor_inactivity": ["start_date", "end_date"],
    "fare_trend": ["start_date", "end_date", "granularity", "metric"],
    "tip_trend": ["start_date", "end_date", "granularity", "metric"],
}
SUPPORTED_INTENTS = set(REQUIRED_SLOTS)


# =============================================================================
# Gemini router setup
# =============================================================================
SYSTEM_PROMPT = f"""
You are a routing assistant.

Dataset:
NYC Yellow Taxi trips for YEAR {DATASET_YEAR} only.

Choose ONE intent:
- trip_frequency
- vendor_inactivity
- fare_trend
- tip_trend
- unknown

If the user asks about churn/customers/cohorts:
- dataset_match = false

Return JSON ONLY:
{{ "intent": "", "dataset_match": true | false }}
""".strip()


def configure_gemini() -> Optional[Any]:
    """
    Runtime helper (NOT required for tests).
    If quota fails or key missing, we return None and CLI will fallback gracefully.
    """
    if genai is None:
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        genai.configure(api_key=api_key)
        # pick first model that supports generateContent
        for m in genai.list_models():
            if "generateContent" in getattr(m, "supported_generation_methods", []):
                return genai.GenerativeModel(m.name)
    except Exception:
        return None

    return None


# IMPORTANT: tests monkeypatch this attribute
MODEL = configure_gemini()


def ask_gemini_router(user_input: str) -> Dict[str, Any]:
    """
    Tests expect:
    - it calls MODEL.generate_content(...)
    - reads response.text
    - parses JSON
    In real life: if MODEL is None or quota error -> fallback deterministic router.
    """
    # --- fallback heuristic router (robust when MODEL missing/quota) ---
    def _fallback() -> Dict[str, Any]:
        t = user_input.lower()
        # out-of-scope
        if any(k in t for k in ["churn", "customer", "cohort", "retention"]):
            return {"intent": "unknown", "dataset_match": False}

        # in-scope heuristics
        if "vendor" in t:
            return {"intent": "vendor_inactivity", "dataset_match": True}
        if "tip" in t:
            return {"intent": "tip_trend", "dataset_match": True}
        if "fare" in t or "price" in t or "expensive" in t:
            return {"intent": "fare_trend", "dataset_match": True}
        if "trip" in t or "rides" in t or "ride" in t or "busy" in t or "frequency" in t:
            return {"intent": "trip_frequency", "dataset_match": True}

        return {"intent": "unknown", "dataset_match": True}

    if MODEL is None:
        return _fallback()

    try:
        response = MODEL.generate_content(SYSTEM_PROMPT + "\n\nUser request:\n" + user_input)
        text = response.text.strip()
        # strip markdown fences if the model returns them
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        return json.loads(text)
    except Exception:
        # quota, parse errors, etc.
        return _fallback()


# =============================================================================
# Normalizers (tests expect these names + outputs)
# =============================================================================
def normalize_granularity(value: str) -> str:
    v = value.strip().lower()
    # accept first token (so "weekly instad" still works)
    v = v.split()[0] if v else v

    if v in ("day", "daily"):
        return "daily"
    if v in ("week", "weekly"):
        return "weekly"
    if v in ("month", "monthly"):
        return "monthly"

    raise ValueError("Invalid granularity. Use daily, weekly, or monthly.")


def normalize_metric(value: str) -> str:
    v = value.strip().lower()
    v = v.split()[0] if v else v

    if v in ("total", "sum"):
        return "total"
    if v in ("avg", "average", "mean"):
        # IMPORTANT: tests expect normalize_metric("avg") == "avg"
        return "avg"

    raise ValueError("Invalid metric. Use avg or total.")


# =============================================================================
# Date parsing + validation (tests expect validate_date + validate_range)
# =============================================================================
def validate_date(date_str: str) -> None:
    """
    Test-facing helper.
    Validates a single date string (YYYY-MM-DD or YYYY/MM/DD) within 2022.
    """
    try:
        dt = _parse_date(date_str)
    except ValueError:
        raise ValueError("Invalid date format. Use something like 2022-06-01 (or 2022/06/01).")

    if not (MIN_DATE <= dt < MAX_DATE):
        raise ValueError("Date must be in 2022.")


def validate_range(start: str, end: str) -> None:
    """
    Test-facing helper.
    Accepts strings; ensures end_date > start_date.
    """
    s = _parse_date(start)
    e = _parse_date(end)

    if not (MIN_DATE <= s < MAX_DATE) or not (MIN_DATE <= e < MAX_DATE):
        raise ValueError("Date must be in 2022.")

    if e <= s:
        raise ValueError("end_date must be AFTER start_date (exclusive).")


def _parse_date(s: str) -> datetime:
    s = s.strip().replace("/", "-")
    return datetime.strptime(s, "%Y-%m-%d")


def _date_to_str(d: Any) -> str:
    """
    Accepts datetime or YYYY-MM-DD string.
    Returns YYYY-MM-DD string.
    """
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        # ensure it is normalized YYYY-MM-DD
        return _parse_date(d).strftime("%Y-%m-%d")
    raise TypeError("start_date/end_date must be datetime or YYYY-MM-DD string")


# =============================================================================
# NLP SLOT EXTRACTION (deterministic; should NOT crash on missing metric)
# =============================================================================
ISO_DATE_RE = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")
MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

Q_RE = re.compile(r"\bq([1-4])\b", re.IGNORECASE)


def extract_dates(text: str) -> List[datetime]:
    dates: List[datetime] = []

    # 1) ISO dates
    for y, m, d in ISO_DATE_RE.findall(text):
        dt = datetime(int(y), int(m), int(d))
        if dt.year == DATASET_YEAR:
            dates.append(dt)

    if dates:
        return sorted(dates)

    # 2) Quarter parsing (e.g., "Q2 2022")
    t = text.lower()
    if "2022" in t:
        qm = Q_RE.search(t)
        if qm:
            q = int(qm.group(1))
            start_month = (q - 1) * 3 + 1
            start = datetime(2022, start_month, 1)
            end_month = start_month + 3
            end = datetime(2022, end_month, 1)
            return [start, end]

    # 3) Month words (e.g., "Feb 2022" or "January to June 2022")
    if "2022" not in t:
        return []

    months = MONTH_RE.findall(t)
    if not months:
        return []

    month_nums = [MONTH_MAP[m[:3].lower()] for m in months]

    # If single month -> [month_start, next_month_start]
    if len(month_nums) == 1:
        m = month_nums[0]
        start = datetime(2022, m, 1)
        end = datetime(2022, m + 1, 1) if m < 12 else datetime(2023, 1, 1)
        return [start, end]

    # If multiple months -> min to max (end is exclusive next month)
    start = datetime(2022, min(month_nums), 1)
    end_month = max(month_nums)
    end = datetime(2022, end_month + 1, 1) if end_month < 12 else datetime(2023, 1, 1)
    return [start, end]


def extract_slots_from_text(user_input: str) -> None:
    """
    Tests rely on this:
    - sets start_date/end_date as datetime
    - sets granularity properly
    - MUST NOT raise just because metric isn't present
    """
    dates = extract_dates(user_input)

    if len(dates) >= 1 and session_state["start_date"] is None:
        session_state["start_date"] = dates[0]
    if len(dates) >= 2 and session_state["end_date"] is None:
        session_state["end_date"] = dates[1]

    text = user_input.lower()

    if session_state["granularity"] is None:
        if "month" in text or "monthly" in text:
            session_state["granularity"] = "monthly"
        elif "week" in text or "weekly" in text:
            session_state["granularity"] = "weekly"
        elif "day" in text or "daily" in text:
            session_state["granularity"] = "daily"

    # metric should only be filled when clearly mentioned
    if session_state["metric"] is None:
        if "total" in text or "sum" in text:
            session_state["metric"] = "total"
        elif "avg" in text or "average" in text or "mean" in text:
            session_state["metric"] = "avg"


# =============================================================================
# SQL safety (tests expect safe_select_only exists + raises on DELETE, etc.)
# =============================================================================
def safe_select_only(sql: str) -> str:
    low = sql.lower().strip()

    # allow WITH ... SELECT ...
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")

    for kw in ("insert", "update", "delete", "drop", "alter", "create"):
        if re.search(rf"\b{kw}\b", low):
            raise ValueError("Unsafe SQL detected.")

    return sql


# =============================================================================
# SQL builders
# =============================================================================
def time_bucket(granularity: str) -> Tuple[str, str]:
    if granularity == "daily":
        return "DATE(pickup_datetime)", "day"
    if granularity == "weekly":
        return "STRFTIME('%Y-%W', pickup_datetime)", "week"
    return "STRFTIME('%Y-%m', pickup_datetime)", "month"


def build_sql(intent: str) -> str:
    sd = _date_to_str(session_state["start_date"])
    ed = _date_to_str(session_state["end_date"])

    if intent == "trip_frequency":
        expr, label = time_bucket(session_state["granularity"])
        return f"""
SELECT {expr} AS {label}, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY 1
ORDER BY 1;
""".strip()

    if intent == "vendor_inactivity":
        return f"""
SELECT vendor_id, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY vendor_id
ORDER BY trips ASC;
""".strip()

    col = "fare_amount" if intent == "fare_trend" else "tip_amount"
    agg = "SUM" if session_state["metric"] == "total" else "AVG"
    expr, label = time_bucket(session_state["granularity"])

    return f"""
SELECT {expr} AS {label}, {agg}({col}) AS value
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY 1
ORDER BY 1;
""".strip()


# =============================================================================
# Helper: missing slots
# =============================================================================
def missing_slots(intent: str) -> List[str]:
    req = REQUIRED_SLOTS.get(intent, [])
    return [k for k in req if session_state.get(k) is None]


def validate_dates() -> None:
    """
    CLI guard: ensures dates are within dataset + ordered.
    Works whether state has datetime or string.
    """
    sd = _date_to_str(session_state["start_date"])
    ed = _date_to_str(session_state["end_date"])
    validate_range(sd, ed)


# =============================================================================
# CLI loop
# =============================================================================
def run_agent():
    global session_state
    print("\n🧠 Symbiote Lite — Analyst Agent\n")

    while True:
        q = input("Ask a data question: ").strip()

        if q.lower() in ("exit", "quit"):
            break
        if q.lower() == "reset":
            session_state = reset_session()
            print("Session reset.\n")
            continue

        # deterministic slot extraction first
        extract_slots_from_text(q)

        # intent routing (Gemini if available; fallback if not)
        if session_state["intent"] is None:
            route = ask_gemini_router(q)

            if not route.get("dataset_match", True):
                print("Out of scope.")
                session_state = reset_session()
                continue

            intent = route.get("intent", "unknown")
            if intent not in SUPPORTED_INTENTS:
                print("Try asking about trips, fares, tips, or vendors in 2022.")
                session_state = reset_session()
                continue

            session_state["intent"] = intent

        # fill missing slots
        for slot in missing_slots(session_state["intent"]):
            if slot == "start_date":
                while True:
                    raw = input("start_date (YYYY-MM-DD): ").strip()
                    try:
                        validate_date(raw)
                        session_state["start_date"] = _parse_date(raw)
                        break
                    except Exception as e:
                        print(f"  ⚠️ {e}")

            elif slot == "end_date":
                while True:
                    raw = input("end_date (YYYY-MM-DD): ").strip()
                    try:
                        validate_date(raw)
                        session_state["end_date"] = _parse_date(raw)
                        break
                    except Exception as e:
                        print(f"  ⚠️ {e}")

            elif slot == "granularity":
                while True:
                    raw = input("granularity (daily/weekly/monthly): ").strip()
                    try:
                        session_state["granularity"] = normalize_granularity(raw)
                        break
                    except Exception as e:
                        print(f"  ⚠️ {e}")

            elif slot == "metric":
                while True:
                    raw = input("metric (avg/total): ").strip()
                    try:
                        session_state["metric"] = normalize_metric(raw)
                        break
                    except Exception as e:
                        print(f"  ⚠️ {e}")

        # validate and run
        try:
            validate_dates()
        except Exception as e:
            print(f"  ⚠️ {e}")
            session_state = reset_session()
            continue

        sql = build_sql(session_state["intent"])
        sql = safe_select_only(sql)

        print("\nSQL:\n", sql)

        if input("\nRun query? (yes/no): ").lower().strip() != "yes":
            session_state = reset_session()
            continue

        df = execute_sql_query(sql)
        print(df.head())
        print("\nDone.\n")

        session_state = reset_session()


if __name__ == "__main__":
    run_agent()
