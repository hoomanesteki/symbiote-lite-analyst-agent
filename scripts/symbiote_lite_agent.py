from __future__ import annotations
"""
Symbiote Lite — Human-in-the-Loop NYC Taxi Analyst (2022)
ENHANCED VERSION with smart guidance, robust edge case handling, and better UX

Improvements:
- Smarter summary mode (doesn't trigger on specific questions)
- Immediate invalid date feedback
- Smart granularity recommendations
- SQL explanations before approval
- Better validation and error handling
- Contextual help system
- Follow-up suggestions
- Empty result handling
"""

# =============================================================================
# Imports
# =============================================================================
import os
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Project root (load .env)
ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

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
    return {
        "intent": None,
        "start_date": None,     # datetime OR "YYYY-MM-DD"
        "end_date": None,       # datetime OR "YYYY-MM-DD" (exclusive)
        "granularity": None,    # daily / weekly / monthly
        "metric": None,         # avg / total
        "_saw_invalid_iso_date": False,
        "_invalid_dates": [],   # Track which dates were invalid
    }

session_state: Dict[str, Any] = reset_session()

# =============================================================================
# Supported intents (SQL-able)
# =============================================================================
REQUIRED_SLOTS = {
    "trip_frequency": ["start_date", "end_date", "granularity"],
    "vendor_inactivity": ["start_date", "end_date"],
    "fare_trend": ["start_date", "end_date", "granularity", "metric"],
    "tip_trend": ["start_date", "end_date", "granularity", "metric"],
}
SUPPORTED_INTENTS = set(REQUIRED_SLOTS)

# =============================================================================
# UX copy
# =============================================================================
INTRO = f"""
🧠 Symbiote Lite — NYC Taxi Analyst ({DATASET_YEAR})

What I can do:
- Turn your question into SAFE, SELECT-only SQL over `taxi_trips`
- Ask 1–2 quick clarifying questions if needed
- Show a short plan + the SQL, then run only after you approve

Data constraints:
- Dates must be in {DATASET_YEAR}
- end_date is EXCLUSIVE (end_date=2022-02-01 includes up to Jan 31)

Examples:
- "show trips from 2022-01-01 to 2022-02-01 by day"
- "were we busier in January vs February 2022?" (I'll ask what "busier" means)
- "how did fares change in summer 2022 by week (avg)"
- "show total tips in Q2 2022 by month"
- "which vendors were inactive in November 2022?"

Commands:
- help  → examples + what to ask
- reset → clear state
- exit  → quit
""".strip()

HELP_TEXT = INTRO

# =============================================================================
# OpenAI (ChatGPT) integration (optional)
# =============================================================================
def _openai_client() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
        return OpenAI()
    except Exception:
        return None

def _openai_model_name() -> str:
    return os.getenv("SYMBIOTE_MODEL", "gpt-5")

class _OpenAIModelShim:
    """
    Shim to look like Gemini's MODEL for tests:
    - has generate_content(prompt) -> object with .text
    Under the hood uses OpenAI Responses API.
    """
    def __init__(self, client: Any):
        self._client = client

    class _Resp:
        def __init__(self, text: str):
            self.text = text

    def generate_content(self, prompt: str) -> Any:
        resp = self._client.responses.create(
            model=_openai_model_name(),
            reasoning={"effort": "low"},
            temperature=0,
            input=prompt,
        )
        return self._Resp(resp.output_text or "")

def configure_chatgpt_model() -> Optional[Any]:
    client = _openai_client()
    if client is None:
        return None
    return _OpenAIModelShim(client)

# IMPORTANT: tests monkeypatch this attribute
MODEL = configure_chatgpt_model()

# =============================================================================
# Prompts for LLM layers
# =============================================================================
ROUTER_SYSTEM_PROMPT = f"""
You are a routing assistant for an NYC Yellow Taxi dataset (YEAR {DATASET_YEAR} only).

Output JSON ONLY:
- intent: one of ["trip_frequency","vendor_inactivity","fare_trend","tip_trend","unknown"]
- dataset_match: true/false

Rules:
- If user asks for other years (e.g. 2023) => dataset_match=false
- If user asks about churn/customers/cohorts => dataset_match=false
- If question is greetings/help/what-can-I-ask/summary/overview => intent="unknown", dataset_match=true

Return JSON only.
""".strip()

REWRITE_SYSTEM_PROMPT = """
You rewrite user messages into a clear, analyst-friendly NYC taxi question for YEAR 2022.
Also extract slot hints if present.

Output JSON ONLY:
{
  "rewritten": "string",
  "intent_hint": "trip_frequency|vendor_inactivity|fare_trend|tip_trend|unknown",
  "granularity_hint": "daily|weekly|monthly|null",
  "metric_hint": "avg|total|null"
}

Notes:
- Keep rewritten short and explicit about dates if user implied (e.g., "summer 2022" -> "2022-06-01 to 2022-09-01")
- If user says "busier" set intent_hint="trip_frequency"
- If user says "summary" or "overview", keep rewritten as a helpful suggestion question.
Return JSON only.
""".strip()

# =============================================================================
# Routing (tests expect ask_gemini_router name)
# =============================================================================
def _heuristic_route(user_input: str) -> Dict[str, Any]:
    t = user_input.lower()

    if any(k in t for k in ["churn", "customer", "cohort", "retention"]):
        return {"intent": "unknown", "dataset_match": False}
    if re.search(r"\b20(1\d|2[0134-9])\b", t) and "2022" not in t:
        return {"intent": "unknown", "dataset_match": False}

    if any(k in t for k in ["help", "what can i ask", "what can i do", "who are you"]):
        return {"intent": "unknown", "dataset_match": True}

    if "vendor" in t:
        return {"intent": "vendor_inactivity", "dataset_match": True}
    if "tip" in t:
        return {"intent": "tip_trend", "dataset_match": True}
    if "fare" in t or "price" in t or "expensive" in t:
        return {"intent": "fare_trend", "dataset_match": True}
    if any(k in t for k in ["trip", "trips", "ride", "rides", "busy", "busier", "frequency"]):
        return {"intent": "trip_frequency", "dataset_match": True}

    return {"intent": "unknown", "dataset_match": True}

def ask_gemini_router(user_input: str) -> Dict[str, Any]:
    if MODEL is None:
        return _heuristic_route(user_input)

    try:
        prompt = ROUTER_SYSTEM_PROMPT + "\n\nUser request:\n" + user_input
        response = MODEL.generate_content(prompt)
        text = (response.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        data = json.loads(text)
        if not isinstance(data, dict):
            return _heuristic_route(user_input)
        return data
    except Exception:
        return _heuristic_route(user_input)

def semantic_rewrite(user_input: str) -> Dict[str, Any]:
    def _fallback() -> Dict[str, Any]:
        return {
            "rewritten": user_input.strip(),
            "intent_hint": _heuristic_route(user_input)["intent"],
            "granularity_hint": None,
            "metric_hint": None,
        }

    if MODEL is None:
        return _fallback()

    try:
        prompt = REWRITE_SYSTEM_PROMPT + "\n\nUser message:\n" + user_input
        resp = MODEL.generate_content(prompt)
        text = (resp.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
        data = json.loads(text)
        if not isinstance(data, dict) or "rewritten" not in data:
            return _fallback()
        return data
    except Exception:
        return _fallback()

# =============================================================================
# Normalizers (tests expect these names + outputs)
# =============================================================================
def normalize_granularity(value: str) -> str:
    v = (value or "").strip().lower()
    v = v.split()[0] if v else v
    if v in ("day", "daily"):
        return "daily"
    if v in ("week", "weekly"):
        return "weekly"
    if v in ("month", "monthly"):
        return "monthly"
    raise ValueError("Choose one: daily, weekly, monthly.")

def normalize_metric(value: str) -> str:
    v = (value or "").strip().lower()
    parts = v.split()
    if not parts:
        raise ValueError("Choose one: avg, total.")
    v = parts[0]
    if v in ("total", "sum"):
        return "total"
    if v in ("avg", "average", "mean"):
        return "avg"
    raise ValueError("Choose one: avg, total.")

# =============================================================================
# Date parsing + validation (tests expect validate_date + validate_range)
# =============================================================================
def _parse_date(s: str) -> datetime:
    s = s.strip().replace("/", "-")
    return datetime.strptime(s, "%Y-%m-%d")

def validate_date(date_str: str) -> None:
    try:
        dt = _parse_date(date_str)
    except Exception:
        raise ValueError("Invalid date. Use YYYY-MM-DD (example: 2022-06-01).")
    if not (MIN_DATE <= dt < MAX_DATE):
        raise ValueError("Date must be in 2022.")

def validate_range(start: str, end: str) -> None:
    s = _parse_date(start)
    e = _parse_date(end)
    if not (MIN_DATE <= s < MAX_DATE) or not (MIN_DATE <= e < MAX_DATE):
        raise ValueError("Date must be in 2022.")
    if e <= s:
        raise ValueError("end_date must be AFTER start_date (end_date is exclusive).")
    
    # ENHANCEMENT: Warn about single-day ranges
    if (e - s).days == 1:
        print(f"\n💡 Note: This is a single-day range ({s.strftime('%Y-%m-%d')} only).")
        print("   Remember: end_date is exclusive.\n")

def _date_to_str(d: Any) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        return _parse_date(d).strftime("%Y-%m-%d")
    raise TypeError("start_date/end_date must be datetime or YYYY-MM-DD string")

# =============================================================================
# Deterministic slot extraction (robust, no crashes)
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

SEASON_MAP = {
    "spring": (3, 6),
    "summer": (6, 9),
    "fall": (9, 12),
    "autumn": (9, 12),
    "winter": (1, 3),
}

def extract_dates(text: str) -> List[datetime]:
    """
    ENHANCED: Immediate feedback on invalid dates
    """
    dates: List[datetime] = []
    invalid_dates: List[str] = []
    found_iso = False

    for y, m, d in ISO_DATE_RE.findall(text):
        found_iso = True
        try:
            dt = datetime(int(y), int(m), int(d))
            if dt.year == DATASET_YEAR:
                dates.append(dt)
        except ValueError:
            invalid_dates.append(f"{y}-{m}-{d}")

    # ENHANCEMENT: Immediate feedback
    if invalid_dates:
        print(f"\n⚠️  Found invalid date(s): {', '.join(invalid_dates)}")
        print("    Tip: Month must be 01-12, day must fit the month")
        print("    Example: 2022-06-15 (June 15th, 2022)\n")
        session_state["_saw_invalid_iso_date"] = True
        session_state["_invalid_dates"] = invalid_dates

    if found_iso and not dates and invalid_dates:
        return []

    if dates:
        return sorted(dates)

    t = text.lower()

    # Quarters
    if "2022" in t:
        qm = Q_RE.search(t)
        if qm:
            q = int(qm.group(1))
            start_month = (q - 1) * 3 + 1
            start = datetime(2022, start_month, 1)
            end = datetime(2022, start_month + 3, 1)
            return [start, end]

    # Seasons - ENHANCEMENT: ask if year missing
    for s, (m1, m2) in SEASON_MAP.items():
        if s in t:
            if "2022" not in t:
                print(f"\n💡 I see '{s}' — did you mean {s} 2022?")
                return []
            return [datetime(2022, m1, 1), datetime(2022, m2, 1)]

    # Month words
    if "2022" not in t:
        return []
    months = MONTH_RE.findall(t)
    if not months:
        return []

    nums = [MONTH_MAP[m[:3].lower()] for m in months]
    if len(nums) == 1:
        m = nums[0]
        start = datetime(2022, m, 1)
        end = datetime(2022, m + 1, 1) if m < 12 else datetime(2023, 1, 1)
        return [start, end]

    start = datetime(2022, min(nums), 1)
    end_m = max(nums)
    end = datetime(2022, end_m + 1, 1) if end_m < 12 else datetime(2023, 1, 1)
    return [start, end]

def extract_slots_from_text(user_input: str) -> None:
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

    if session_state["metric"] is None:
        if "total" in text or "sum" in text:
            session_state["metric"] = "total"
        elif "avg" in text or "average" in text or "mean" in text:
            session_state["metric"] = "avg"

# =============================================================================
# SQL safety (tests expect safe_select_only)
# =============================================================================
def safe_select_only(sql: str) -> str:
    low = sql.lower().strip()
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
# ENHANCEMENT: Smart recommendations
# =============================================================================
def recommend_granularity(start: datetime, end: datetime) -> str:
    """Suggest granularity based on date range"""
    days = (end - start).days
    
    if days <= 7:
        return "daily"
    elif days <= 90:
        return "weekly"
    else:
        return "monthly"

def estimate_rows(intent: str, start: datetime, end: datetime, granularity: Optional[str]) -> str:
    """Estimate result rows for user"""
    if intent == "vendor_inactivity":
        return "~3-5"
    
    if not granularity:
        return "unknown"
    
    days = (end - start).days
    if granularity == "daily":
        return f"~{days}"
    elif granularity == "weekly":
        return f"~{days // 7}"
    else:
        return f"~{days // 30}"

def explain_sql(intent: str) -> str:
    """Human-readable SQL explanation"""
    metric = session_state.get("metric")
    explanations = {
        "trip_frequency": "Count how many taxi trips occurred in each time bucket",
        "vendor_inactivity": "Rank taxi vendors by total trips (fewest first = most inactive)",
        "fare_trend": f"Calculate {'total sum' if metric=='total' else 'average'} of fare amounts per time bucket",
        "tip_trend": f"Calculate {'total sum' if metric=='total' else 'average'} of tip amounts per time bucket",
    }
    return explanations.get(intent, "Run analysis query")

def suggest_followup(intent: str) -> None:
    """Context-aware follow-up suggestions"""
    suggestions = {
        "trip_frequency": [
            "Compare this to another period",
            "See which vendors drove these trips",
            "Check fare trends for the same period",
        ],
        "vendor_inactivity": [
            "See trip trends for the most inactive vendor",
            "Compare vendor activity across quarters",
        ],
        "fare_trend": [
            "Compare to trip frequency (correlation?)",
            "See tip trends for the same period",
        ],
        "tip_trend": [
            "Compare to fare trends (tip percentage)",
            "See which vendors have highest tips",
        ],
    }
    
    items = suggestions.get(intent, [])
    if items:
        print("\n💡 You might also want to:")
        for i, s in enumerate(items, 1):
            print(f"   {i}. {s}")
        print()

# =============================================================================
# Helpers
# =============================================================================
def missing_slots(intent: str) -> List[str]:
    req = REQUIRED_SLOTS.get(intent, [])
    return [k for k in req if session_state.get(k) is None]

def validate_dates_state() -> None:
    sd = _date_to_str(session_state["start_date"])
    ed = _date_to_str(session_state["end_date"])
    validate_range(sd, ed)

def validate_all_slots() -> bool:
    """ENHANCEMENT: Final sanity check before SQL"""
    try:
        validate_dates_state()
        
        intent = session_state["intent"]
        if intent in ["trip_frequency", "fare_trend", "tip_trend"]:
            if not session_state.get("granularity"):
                print("⚠️  Internal error: missing granularity")
                return False
        
        if intent in ["fare_trend", "tip_trend"]:
            if not session_state.get("metric"):
                print("⚠️  Internal error: missing metric")
                return False
        
        return True
    except Exception as e:
        print(f"⚠️  Validation failed: {e}")
        return False

def _prompt_choice(prompt: str, choices: List[str], default: Optional[str] = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{prompt}{suffix}: ").strip().lower()
        if not raw and default:
            return default
        raw = raw.split()[0] if raw else raw
        if raw in choices:
            return raw
        print(f"  ⚠️  Choose one: {', '.join(choices)}.")

def _prompt_yes_no(prompt: str) -> bool:
    while True:
        raw = input(f"{prompt} (yes/no): ").strip().lower()
        if raw in ("yes", "y"):
            return True
        if raw in ("no", "n"):
            return False
        print("  ⚠️  Please type yes or no.")

def _prompt_date(field: str, example: str) -> datetime:
    while True:
        raw = input(f"{field} (YYYY-MM-DD, 2022 only) e.g. {example}: ").strip()
        try:
            validate_date(raw)
            return _parse_date(raw)
        except Exception as e:
            print(f"  ⚠️  {e}")

# =============================================================================
# ENHANCEMENT: Smarter meta + guidance handling
# =============================================================================
SUMMARY_FUZZY_RE = re.compile(r"\bsumm(?:ary|ar|er|ery|ize|ised|ized)?\b", re.I)
HELPISH_RE = re.compile(r"\b(help|what can i ask|what can i do|how can you help|how can u help|who are you|your name)\b", re.I)

def _is_summaryish(text: str) -> bool:
    return bool(SUMMARY_FUZZY_RE.search(text))

def _has_specific_topic(text: str) -> bool:
    """Check if user mentioned a specific topic"""
    t = text.lower()
    return any(word in t for word in ["fare", "fares", "tip", "tips", "trip", "trips", "vendor", "vendors"])

def _needs_summary_wizard(text: str) -> bool:
    """ENHANCEMENT: Only trigger wizard if vague + summary keyword"""
    return _is_summaryish(text) and not _has_specific_topic(text)

def _handle_summary_wizard() -> Optional[str]:
    """
    Returns a rewritten analytic question string, or None if user cancels.
    """
    print("\n🧾 Summary mode — I can summarize a period, but I need 2 things:")
    print("1) Topic: trips / fares / tips / vendors")
    print("2) Period: e.g., summer 2022, Q2 2022, November 2022, or 2022-01-01 to 2022-02-01\n")

    topic = _prompt_choice("Topic (trips/fares/tips/vendors)", ["trips", "fares", "tips", "vendors"], default="trips")
    period = input("Period (example: summer 2022): ").strip()
    if not period:
        print("  ⚠️  Please provide a period (like 'summer 2022' or '2022-01-01 to 2022-02-01').\n")
        return None

    gran = "monthly"

    if topic == "trips":
        return f"show trips in {period} by {gran}"
    if topic == "vendors":
        return f"which vendors were inactive in {period}"
    
    print("\nMetric controls how we aggregate money:")
    print("  - avg   = average per trip")
    print("  - total = total sum in the period")
    metric = _prompt_choice("Metric (avg/total)", ["avg", "total"], default="avg")
    if topic == "fares":
        return f"show {metric} fares in {period} by {gran}"
    return f"show {metric} tips in {period} by {gran}"

def contextual_help(user_input: str) -> None:
    """ENHANCEMENT: Context-aware help"""
    t = user_input.lower()
    
    if "date" in t or "when" in t:
        print("\n📅 Date format: YYYY-MM-DD (example: 2022-06-15)")
        print("Shortcuts:")
        print("  • 'summer 2022' = June-August")
        print("  • 'Q2 2022' = April-June")
        print("  • 'November 2022' = full month\n")
    elif "granularity" in t:
        print("\n📊 Granularity = time bucket size:")
        print("  • daily   = one row per day")
        print("  • weekly  = one row per week")
        print("  • monthly = one row per month")
        print("Use finer granularity for short periods.\n")
    elif "metric" in t:
        print("\n💰 Metric = how to aggregate money:")
        print("  • avg   = average per trip (e.g., $15.23/trip)")
        print("  • total = sum over all trips (e.g., $50,000 total)")
        print("Use 'total' to see revenue, 'avg' to see typical amounts.\n")
    else:
        print("\n" + HELP_TEXT + "\n")

def _handle_meta_or_guidance(user_input: str) -> Optional[str]:
    """
    Returns:
    - a rewritten analytic question (string) if we should continue
    - "" if handled fully
    - None if not a meta/guidance input
    """
    t = user_input.strip().lower()

    if t == "help" or "help" in t:
        contextual_help(user_input)
        return ""

    if HELPISH_RE.search(t):
        print("\nHi! I'm Symbiote Lite. I help you analyze NYC Yellow Taxi trips in 2022.\n")
        print("Try: \"show trips from 2022-01-01 to 2022-02-01 by day\"")
        print("Or type 'help' for examples.\n")
        return ""

    # ENHANCEMENT: Only trigger wizard if truly vague
    if _needs_summary_wizard(t):
        rewritten = _handle_summary_wizard()
        return rewritten if rewritten else ""

    return None

def _clarify_busier() -> str:
    print("\n❓ Quick clarification:")
    print("When you say *busier*, do you mean:")
    print("  1) Number of trips")
    print("  2) Total fares")
    print("  3) Average fare")
    while True:
        raw = input("Choose 1/2/3: ").strip()
        if raw == "1":
            return "trip_frequency"
        if raw == "2":
            session_state["metric"] = "total"
            return "fare_trend"
        if raw == "3":
            session_state["metric"] = "avg"
            return "fare_trend"
        print("  ⚠️  Choose 1, 2, or 3.")

# =============================================================================
# CLI loop
# =============================================================================
def run_agent():
    global session_state

    print("\n" + INTRO + "\n")

    # Show mode
    if os.getenv("OPENAI_API_KEY"):
        if MODEL is None:
            print("⚠️  OPENAI_API_KEY is set, but OpenAI client/model is not available. Falling back to deterministic mode.\n")
        else:
            print("✅ ChatGPT routing is enabled (OpenAI).\n")
    else:
        print("ℹ️  ChatGPT routing is OFF (no OPENAI_API_KEY). Using deterministic mode.\n")

    # ENHANCEMENT: First-time user hint
    if not os.path.exists(".symbiote_history"):
        print("👋 First time here? Try: \"show trips in January 2022 by week\"\n")
        try:
            with open(".symbiote_history", "w") as f:
                f.write("visited")
        except Exception:
            pass

    while True:
        q = input("Ask a question: ").strip()
        if not q:
            continue

        if q.lower() in ("exit", "quit"):
            break
        if q.lower() == "reset":
            session_state = reset_session()
            print("Session reset.\n")
            continue

        # Meta/guidance & summary wizard first
        meta = _handle_meta_or_guidance(q)
        if meta is not None:
            if meta == "":
                continue
            else:
                q = meta

        # Reset per analytic turn
        session_state = reset_session()

        # Semantic rewrite (optional)
        rewrite = semantic_rewrite(q)
        rewritten = (rewrite.get("rewritten") or q).strip()

        # ENHANCEMENT: Use LLM hints to pre-fill slots
        gh = rewrite.get("granularity_hint")
        if gh and gh in ("daily", "weekly", "monthly"):
            session_state["granularity"] = gh
        
        mh = rewrite.get("metric_hint")
        if mh and mh in ("avg", "total"):
            session_state["metric"] = mh

        # Deterministic extraction (adds to LLM hints)
        extract_slots_from_text(rewritten)

        # ENHANCEMENT: If invalid dates detected, force clean re-entry
        if session_state.get("_saw_invalid_iso_date"):
            print("  Let's enter valid dates.\n")
            session_state["start_date"] = None
            session_state["end_date"] = None

        # Route
        route = ask_gemini_router(rewritten)
        if not route.get("dataset_match", True):
            print("\n❌ Out of scope for this dataset (NYC Yellow Taxi 2022).")
            print("Try asking about trips/fares/tips/vendors in 2022.\n")
            continue

        intent = route.get("intent", "unknown")
        if intent not in SUPPORTED_INTENTS:
            if "busier" in q.lower() or "busy" in q.lower():
                intent = _clarify_busier()
            else:
                print("\nI can help with NYC taxi data in 2022.")
                print("Are you trying to analyze trips, fares, tips, or vendors?")
                print("Type 'help' to see examples.\n")
                continue

        session_state["intent"] = intent

        # Prompt missing slots
        for slot in missing_slots(intent):
            if slot == "start_date":
                session_state["start_date"] = _prompt_date("start_date", "2022-06-01")
            elif slot == "end_date":
                session_state["end_date"] = _prompt_date("end_date", "2022-09-01")
            elif slot == "granularity":
                # ENHANCEMENT: Smart default
                if session_state["start_date"] and session_state["end_date"]:
                    suggestion = recommend_granularity(
                        session_state["start_date"],
                        session_state["end_date"]
                    )
                    days = (session_state["end_date"] - session_state["start_date"]).days
                    print(f"\n💡 For a {days}-day range, '{suggestion}' often works well.")
                else:
                    suggestion = "weekly"
                
                session_state["granularity"] = _prompt_choice(
                    "granularity (daily/weekly/monthly)",
                    ["daily", "weekly", "monthly"],
                    default=suggestion,
                )
            elif slot == "metric":
                print("\nMetric controls how we aggregate money:")
                print("  - avg   = average per trip")
                print("  - total = total sum in the period")
                session_state["metric"] = _prompt_choice(
                    "metric (avg/total)",
                    ["avg", "total"],
                    default="avg",
                )

        # Validate dates
        try:
            validate_dates_state()
        except Exception as e:
            print(f"\n  ⚠️  {e}")
            print("Let's fix the dates.\n")
            session_state["start_date"] = _prompt_date("start_date", "2022-06-01")
            session_state["end_date"] = _prompt_date("end_date", "2022-09-01")
            try:
                validate_dates_state()
            except Exception as e2:
                print(f"\n  ⚠️  {e2}\nCancelled.\n")
                continue

        # ENHANCEMENT: Final validation
        if not validate_all_slots():
            print("Cannot proceed. Please try again.\n")
            continue

        # ENHANCEMENT: Warn about very long daily ranges
        if session_state.get("granularity") == "daily":
            days = (session_state["end_date"] - session_state["start_date"]).days
            if days > 90:
                print(f"\n⚠️  Daily granularity for {days} days = many rows.")
                print("   Consider 'weekly' or 'monthly' for clearer trends.")
                if not _prompt_yes_no("Continue with daily?"):
                    session_state["granularity"] = _prompt_choice(
                        "Choose different granularity",
                        ["weekly", "monthly"],
                        default="weekly",
                    )

        # Enhanced plan display
        sd = _date_to_str(session_state["start_date"])
        ed = _date_to_str(session_state["end_date"])
        gran = session_state.get("granularity")
        metric = session_state.get("metric")

        what = {
            "trip_frequency": "Count trips over time",
            "vendor_inactivity": "Rank vendors by trip count (lowest = most inactive)",
            "fare_trend": f"{'Sum' if metric=='total' else 'Average'} fares over time",
            "tip_trend": f"{'Sum' if metric=='total' else 'Average'} tips over time",
        }[intent]

        rows = estimate_rows(intent, session_state["start_date"], session_state["end_date"], gran)

        print("\n" + "="*60)
        print("🧠 EXECUTION PLAN")
        print("="*60)
        print(f"📌 Task: {what}")
        print(f"📅 Period: {sd} to {ed} (exclusive)")
        if gran:
            print(f"⏱️  Granularity: {gran}")
        if metric and intent in ("fare_trend", "tip_trend"):
            print(f"📊 Metric: {metric}")
        print(f"💾 Expected output: {rows} rows")
        print("="*60 + "\n")

        if not _prompt_yes_no("Does this look correct?"):
            print("Cancelled.\n")
            continue

        # ENHANCEMENT: SQL explanation
        print(f"\n📊 What this query does:")
        print(f"   {explain_sql(intent)}\n")

        sql = safe_select_only(build_sql(intent))
        print("SQL:")
        print(sql)
        print()

        if not _prompt_yes_no("Run query?"):
            print("Cancelled.\n")
            continue

        # Execute with error handling
        print("⏳ Running query...")
        try:
            df = execute_sql_query(sql)
            print("✅ Query complete!\n")
        except Exception as e:
            print(f"\n❌ Query failed: {e}")
            print("This might be a bug — please report it.\n")
            continue

        # ENHANCEMENT: Handle empty results
        if len(df) == 0:
            print("⚠️  Query returned 0 rows.")
            print("Possible reasons:")
            print("  • Date range has no data in the dataset")
            print("  • Try expanding the date range")
            print("  • Verify dates are in 2022\n")
            continue

        print(df.head(20))  # Show more rows
        print(f"\nDone. Returned {len(df)} rows.\n")

        # ENHANCEMENT: Follow-up suggestions
        suggest_followup(intent)

        session_state = reset_session()

if __name__ == "__main__":
    run_agent()