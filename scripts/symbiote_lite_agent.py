from __future__ import annotations
"""
Symbiote Lite — Human-in-the-Loop Analyst Agent (Gemini + SQLite)

Key design:
- LLM = intent routing ONLY
- Slot extraction = deterministic NLP (regex + months)
- SQL = deterministic & safe
- Ask follow-ups ONLY when information is truly missing
"""

# =============================================================================
# Environment (explicit & reproducible)
# =============================================================================
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# =============================================================================
# Standard library
# =============================================================================
import os
import json
import re
from datetime import datetime
from typing import Any, Tuple, List

# =============================================================================
# Third-party
# =============================================================================
import google.generativeai as genai

# Package-relative import
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
def reset_session() -> dict[str, Any]:
    return {
        "intent": None,
        "start_date": None,     # datetime
        "end_date": None,       # datetime (exclusive)
        "granularity": None,    # daily / weekly / monthly
        "metric": None,         # avg / total
    }


session_state: dict[str, Any] = reset_session()


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
# Gemini setup (dynamic, robust)
# =============================================================================
def configure_gemini() -> genai.GenerativeModel:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")

    genai.configure(api_key=api_key)

    for m in genai.list_models():
        if "generateContent" in m.supported_generation_methods:
            print(f"✅ Using Gemini model: {m.name}")
            return genai.GenerativeModel(m.name)

    raise RuntimeError("No Gemini model supporting generateContent found")


MODEL = configure_gemini()


SYSTEM_PROMPT = f"""
You are a routing assistant.

Dataset:
NYC Yellow Taxi trips (sample) for YEAR {DATASET_YEAR}.

Choose ONE intent:
- trip_frequency
- vendor_inactivity
- fare_trend
- tip_trend
- unknown

If the user asks about churn or customers:
- dataset_match = false

Return JSON ONLY:
{{ "intent": "", "dataset_match": true | false }}
""".strip()


# =============================================================================
# Gemini router (intent only)
# =============================================================================
def ask_gemini_router(user_input: str) -> dict[str, Any]:
    response = MODEL.generate_content(
        SYSTEM_PROMPT + "\n\nUser request:\n" + user_input
    )
    text = response.text.strip()
    text = re.sub(r"^```.*?\n|\n```$", "", text, flags=re.S)

    try:
        return json.loads(text)
    except Exception:
        return {"intent": "unknown", "dataset_match": True}


# =============================================================================
# NLP SLOT EXTRACTION (FIXED & TESTABLE)
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


def extract_dates(text: str) -> List[datetime]:
    """
    Deterministically extract dates from text.
    Handles:
    - YYYY-MM-DD / YYYY/MM/DD
    - January to June 2022
    - Feb 2022
    """
    dates: List[datetime] = []

    # --- 1) ISO dates ---
    for y, m, d in ISO_DATE_RE.findall(text):
        dt = datetime(int(y), int(m), int(d))
        if dt.year == DATASET_YEAR:
            dates.append(dt)

    if dates:
        return sorted(dates)

    # --- 2) Month-based parsing ---
    text_lower = text.lower()
    if str(DATASET_YEAR) not in text_lower:
        return []

    months = MONTH_RE.findall(text_lower)
    if not months:
        return []

    month_nums = [MONTH_MAP[m[:3].lower()] for m in months]

    start = datetime(DATASET_YEAR, min(month_nums), 1)
    end_month = max(month_nums)
    end = (
        datetime(DATASET_YEAR, end_month + 1, 1)
        if end_month < 12
        else datetime(DATASET_YEAR + 1, 1, 1)
    )

    return [start, end]


def extract_slots_from_text(user_input: str) -> None:
    dates = extract_dates(user_input)

    if len(dates) >= 1 and session_state["start_date"] is None:
        session_state["start_date"] = dates[0]
    if len(dates) >= 2 and session_state["end_date"] is None:
        session_state["end_date"] = dates[1]

    text = user_input.lower()

    if session_state["granularity"] is None:
        if "month" in text:
            session_state["granularity"] = "monthly"
        elif "week" in text:
            session_state["granularity"] = "weekly"
        elif "day" in text:
            session_state["granularity"] = "daily"

    if session_state["metric"] is None:
        if "total" in text or "sum" in text:
            session_state["metric"] = "total"
        elif "avg" in text or "average" in text or "mean" in text:
            session_state["metric"] = "avg"


# =============================================================================
# Validation
# =============================================================================
def validate_dates():
    if session_state["start_date"] and session_state["end_date"]:
        if not (
            MIN_DATE <= session_state["start_date"]
            < session_state["end_date"]
            <= MAX_DATE
        ):
            raise ValueError("Dates must be within 2022 and end_date > start_date")


def missing_slots(intent: str) -> list[str]:
    return [s for s in REQUIRED_SLOTS[intent] if session_state.get(s) is None]


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
    sd = session_state["start_date"].strftime("%Y-%m-%d")
    ed = session_state["end_date"].strftime("%Y-%m-%d")

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

        extract_slots_from_text(q)

        if session_state["intent"] is None:
            route = ask_gemini_router(q)
            if not route.get("dataset_match", True):
                print("That question is out of scope.")
                session_state = reset_session()
                continue

            intent = route.get("intent", "unknown")
            if intent not in SUPPORTED_INTENTS:
                print("Try asking about trips, fares, tips, or vendors in 2022.")
                session_state = reset_session()
                continue

            session_state["intent"] = intent

        for slot in missing_slots(session_state["intent"]):
            if "date" in slot:
                session_state[slot] = datetime.strptime(
                    input(f"{slot} (YYYY-MM-DD): "),
                    "%Y-%m-%d",
                )
            elif slot == "granularity":
                session_state[slot] = input("granularity (daily/weekly/monthly): ").lower()
            elif slot == "metric":
                session_state[slot] = input("metric (avg/total): ").lower()

        validate_dates()

        sql = build_sql(session_state["intent"])
        print("\nSQL:\n", sql)

        if input("\nRun query? (yes/no): ").lower() != "yes":
            session_state = reset_session()
            continue

        df = execute_sql_query(sql)
        print(df.head())
        print("\nDone.\n")

        session_state = reset_session()


if __name__ == "__main__":
    run_agent()
