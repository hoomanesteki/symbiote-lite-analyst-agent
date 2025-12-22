from __future__ import annotations
"""
Symbiote Lite — Human-in-the-Loop NYC Taxi Analyst (2022)
COMPREHENSIVE VERSION - All edge cases, security, warnings, error handling
Features:
- Smart date extraction with typo tolerance (janurary -> january)
- SQL injection detection and blocking
- Unsupported query detection (weekends, hourly, location)
- Multi-topic detection (trips AND fares -> ask which one)
- Busier/comparison clarification
- Numbered follow-up handling with stale context detection
- Vague time reference handling (last month, recently)
- Summary wizard for insight requests
- Granularity recommendations and warnings
- Empty result handling
- Graceful error handling throughout
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
ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env")
from .analysis import execute_sql_query
# =============================================================================
# Dataset constraints
# =============================================================================
DATASET_YEAR = 2022
MIN_DATE = datetime(2022, 1, 1)
MAX_DATE = datetime(2023, 1, 1)
# =============================================================================
# Session state
# =============================================================================
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
        "_query_count": 0,  # Track queries for stale context detection
        "_last_sql": None,
        "_last_df": None,
        "_last_df_rows": 0,
        "_last_user_question": None,
        "_postprocess": None,
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
    "sample_rows": ["start_date", "end_date"],
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
# OpenAI integration
# =============================================================================
def _openai_client() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None
def _openai_model_name() -> str:
    return os.getenv("SYMBIOTE_MODEL", "gpt-4")
class _OpenAIModelShim:
    def __init__(self, client: Any):
        self._client = client
    class _Resp:
        def __init__(self, text: str):
            self.text = text
    def generate_content(self, prompt: str) -> Any:
        try:
            resp = self._client.responses.create(
                model=_openai_model_name(),
                reasoning={"effort": "low"},
                temperature=0,
                input=prompt,
            )
            return self._Resp(resp.output_text or "")
        except Exception:
            try:
                resp = self._client.chat.completions.create(
                    model=_openai_model_name(),
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}],
                )
                return self._Resp(resp.choices[0].message.content or "")
            except Exception:
                return self._Resp("")
def configure_chatgpt_model() -> Optional[Any]:
    client = _openai_client()
    if client is None:
        return None
    return _OpenAIModelShim(client)
MODEL = configure_chatgpt_model()
# =============================================================================
# LLM Prompts
# =============================================================================
ROUTER_SYSTEM_PROMPT = f"""
You are a routing assistant for an NYC Yellow Taxi dataset (YEAR {DATASET_YEAR} only).
Output JSON ONLY:
- intent: one of ["trip_frequency","vendor_inactivity","fare_trend","tip_trend","sample_rows","unknown"]
- dataset_match: true/false
Return JSON only.
""".strip()
REWRITE_SYSTEM_PROMPT = """
You rewrite user messages into a clear, analyst-friendly NYC taxi question for YEAR 2022.
Output JSON ONLY:
{"rewritten": "string", "intent_hint": "...", "granularity_hint": "...", "metric_hint": "..."}
Return JSON only.
""".strip()
# =============================================================================
# SECURITY: SQL injection detection
# =============================================================================
SQL_INJECTION_PATTERNS = [
    r";\s*drop\s+", r";\s*delete\s+", r";\s*insert\s+", r";\s*update\s+",
    r";\s*alter\s+", r";\s*create\s+", r";\s*truncate\s+", r"--\s*$",
    r"'\s*;\s*", r"'\s*or\s+['\"1]", r"'\s*and\s+", r"union\s+select",
    r"exec\s*\(", r"execute\s*\(", r"xp_\w+", r"sp_\w+",
    r"0x[0-9a-f]+", r"char\s*\(", r"concat\s*\(",
]
def detect_sql_injection(user_input: str) -> bool:
    """Detect potential SQL injection attempts."""
    t = user_input.lower()
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False
# =============================================================================
# UNSUPPORTED QUERY PATTERNS
# =============================================================================
UNSUPPORTED_PATTERNS = [
    (r"\b(weekend|weekday|saturday|sunday|weekends|weekdays)\s.*(busy|busier|more|less|compar|vs|than)", 
     "⚠️  Weekend vs weekday breakdown isn't supported yet.\nI can show you daily data so you can see patterns, or try weekly/monthly aggregation."),
    (r"\b(hour|hourly|morning|evening|afternoon|night|midnight|noon)\b",
     "⚠️  Hourly breakdown isn't supported yet.\nTry: daily, weekly, or monthly granularity instead."),
    (r"\b(location|borough|zone|pickup.?location|dropoff.?location|manhattan|brooklyn|queens|bronx|staten)\b",
     "⚠️  Location-based analysis isn't supported yet.\nI can analyze trips, fares, tips, and vendors over time."),
    (r"\b(driver|drivers|driver.?id)\b",
     "⚠️  Driver-level analysis isn't available.\nI can show vendor (company) level data instead."),
    (r"\b(passenger|passengers|rider|riders)\b",
     "⚠️  Passenger-level analysis isn't available.\nI can analyze trip counts, fares, and tips over time."),
    (r"\b(distance|mile|miles|km|kilometer)\b",
     "⚠️  Distance-based analysis isn't supported yet.\nTry: fare trends or trip counts instead."),
    (r"\b(payment|cash|card|credit|debit)\b",
     "⚠️  Payment type breakdown isn't supported yet.\nI can analyze total fares, tips, and trip counts."),
]
def detect_unsupported_query(user_input: str) -> Optional[str]:
    """Return explanation if query asks for unsupported feature."""
    t = user_input.lower()
    for pattern, explanation in UNSUPPORTED_PATTERNS:
        if re.search(pattern, t):
            return explanation
    return None
# =============================================================================
# MULTI-TOPIC DETECTION
# =============================================================================
def detect_multi_topic(user_input: str) -> Optional[List[str]]:
    """Detect if user asked for multiple topics at once."""
    t = user_input.lower()
    topics_found = []
    
    # Only trigger if explicit conjunction
    if " and " in t or ", " in t:
        if any(w in t for w in ["trip", "trips", "ride", "rides"]):
            topics_found.append("trips")
        if any(w in t for w in ["fare", "fares", "revenue", "money", "price"]):
            topics_found.append("fares")
        if any(w in t for w in ["tip", "tips", "tipping"]):
            topics_found.append("tips")
        if any(w in t for w in ["vendor", "vendors", "company", "companies"]):
            topics_found.append("vendors")
    
    # Only return if genuinely multiple topics
    if len(topics_found) >= 2:
        return topics_found
    return None
# =============================================================================
# Routing
# =============================================================================
def _heuristic_route(user_input: str) -> Dict[str, Any]:
    t = user_input.lower()
    
    # If the user provides valid 2022 dates but forgets the keyword (common follow-up like "use ... instead"),
    # keep the conversation going by assuming a trip count query.
    if "2022-" in t and any(w in t for w in ["use ", "instead", "revise", "change", "update"]) and ("trip" not in t and "fare" not in t and "tip" not in t and "vendor" not in t):
        return {"intent": "trip_frequency"}

    # Out of scope
    if any(k in t for k in ["churn", "customer", "cohort", "retention", "subscription"]):
        return {"intent": "unknown", "dataset_match": False}
    if re.search(r"\b20(1\d|2[0134-9])\b", t) and "2022" not in t:
        return {"intent": "unknown", "dataset_match": False}
    
    # Help/meta
    if any(k in t for k in ["help", "what can i ask", "what can i do", "who are you"]):
        return {"intent": "unknown", "dataset_match": True}
    # Follow-ups / UX commands (sample, compare, explain)
    if any(k in t for k in ["sample", "show me a sample", "limit"]) and any(k in t for k in ["row", "rows", "records"]):
        return {"intent": "sample_rows", "dataset_match": True}
    if "best day" in t and any(k in t for k in ["travel", "go", "ride"]):
        # We'll treat this as a fare-based question by default
        return {"intent": "fare_trend", "dataset_match": True}
    if any(k in t for k in ["compare", "versus", "vs"]):
        # Likely still a supported topic; fall through to topic detection below
        pass
    
    # Trip-related
    if any(k in t for k in ["taxi activity", "trip trends", "breakdown", "spot trends", 
                            "whole year", "entire year", "all of 2022", "full year"]):
        return {"intent": "trip_frequency", "dataset_match": True}
    
    # Specific intents
    if "vendor" in t:
        return {"intent": "vendor_inactivity", "dataset_match": True}
    if "tip" in t and "strip" not in t:  # Avoid false positive
        return {"intent": "tip_trend", "dataset_match": True}
    if any(k in t for k in ["fare", "price", "expensive", "money", "revenue", "cost"]):
        return {"intent": "fare_trend", "dataset_match": True}
    if any(k in t for k in ["trip", "trips", "ride", "rides", "busy", "busier", 
                            "frequency", "activity", "volume"]):
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
    def _fallback():
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
# Normalizers
# =============================================================================
def normalize_granularity(value: str) -> str:
    """Normalize user granularity input with light typo-tolerance.

    Accepts:
      - daily: day, daily, d, days, dialy, daliy
      - weekly: week, weekly, w, weeks, wekly, weekely
      - monthly: month, monthly, m, months, montly, monthy

    Also accepts first-letter shortcuts and common misspellings.
    """
    v = (value or "").strip().lower()
    if not v:
        raise ValueError("Choose one: daily, weekly, monthly.")
    token = v.split()[0]

    # Common misspellings / variants
    if token in ("dialy", "daliy", "dailly"):
        token = "daily"
    if token in ("wekly", "weekely", "weekley"):
        token = "weekly"
    if token in ("montly", "monthy", "monthyl"):
        token = "monthly"

    # First-letter shorthand (d/w/m)
    if token in ("d", "day", "days", "daily"):
        return "daily"
    if token in ("w", "week", "weeks", "weekly"):
        return "weekly"
    if token in ("m", "month", "months", "monthly"):
        return "monthly"

    # Gentle fuzzy: allow prefix like 'weekl' or 'dai'
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
# =============================================================================
# Date parsing and validation
# =============================================================================
def _parse_date(s: str) -> datetime:
    s = s.strip().replace("/", "-")
    return datetime.strptime(s, "%Y-%m-%d")
def validate_date(date_str: str) -> None:
    try:
        dt = _parse_date(date_str)
    except Exception:
        raise ValueError("Invalid date format. Use YYYY-MM-DD (example: 2022-06-01).")
    if not (MIN_DATE <= dt < MAX_DATE):
        raise ValueError(f"Date must be in {DATASET_YEAR}.")
def validate_range(start: str, end: str) -> None:
    s, e = _parse_date(start), _parse_date(end)
    if not (MIN_DATE <= s < MAX_DATE) or not (MIN_DATE <= e <= MAX_DATE):
        raise ValueError(f"Dates must be in {DATASET_YEAR}.")
    if e <= s:
        raise ValueError("end_date must be AFTER start_date (end_date is exclusive).")
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
# Date extraction with typo tolerance
# =============================================================================
ISO_DATE_RE = re.compile(r"\b(\d{4})[-/](\d{2})[-/](\d{2})\b")
Q_RE = re.compile(r"\bq([1-4])\b", re.IGNORECASE)
SEASON_MAP = {
    "spring": (3, 6), "summer": (6, 9), "fall": (9, 12), 
    "autumn": (9, 12), "winter": (1, 3),
}
# COMPREHENSIVE month map with typos
MONTH_MAP = {
    # January variations
    "jan": 1, "january": 1, "janurary": 1, "janury": 1, "januarry": 1, "janaury": 1,
    # February variations
    "feb": 2, "february": 2, "febuary": 2, "feburary": 2, "februrary": 2, "febrary": 2,
    # March variations
    "mar": 3, "march": 3, "mach": 3, "mrch": 3,
    # April variations
    "apr": 4, "april": 4, "apirl": 4, "apil": 4,
    # May
    "may": 5,
    # June variations
    "jun": 6, "june": 6, "juen": 6,
    # July variations
    "jul": 7, "july": 7, "jully": 7,
    # August variations
    "aug": 8, "august": 8, "agust": 8, "augst": 8,
    # September variations
    "sep": 9, "sept": 9, "september": 9, "septmber": 9, "setember": 9,
    # October variations
    "oct": 10, "october": 10, "octobor": 10, "ocotber": 10,
    # November variations
    "nov": 11, "november": 11, "novemeber": 11, "novmber": 11,
    # December variations
    "dec": 12, "december": 12, "decmber": 12, "dicember": 12,
}
def _get_month_num(word: str) -> int:
    """Get month number from word, with typo tolerance."""
    w = word.lower().strip()
    
    # Direct match
    if w in MONTH_MAP:
        return MONTH_MAP[w]
    
    # Try first 3 letters
    if len(w) >= 3:
        prefix = w[:3]
        if prefix in MONTH_MAP:
            return MONTH_MAP[prefix]
    
    # Fuzzy: check if starts similarly to any month
    for key, val in MONTH_MAP.items():
        if len(key) >= 3 and len(w) >= 3:
            if key[:3] == w[:3]:
                return val
    
    return 0
def _find_months_in_text(text: str) -> List[int]:
    """Find all month references in text, including typos."""
    found = []
    words = re.findall(r'\b[a-zA-Z]{3,12}\b', text.lower())
    for word in words:
        month_num = _get_month_num(word)
        if month_num > 0 and month_num not in found:
            found.append(month_num)
    return found
def extract_dates(text: str) -> List[datetime]:
    """Extract dates from text with comprehensive pattern matching."""
    dates, invalid_dates, found_iso = [], [], False
    
    # 1. ISO dates (YYYY-MM-DD)
    for y, m, d in ISO_DATE_RE.findall(text):
        found_iso = True
        try:
            dt = datetime(int(y), int(m), int(d))
            if dt.year == DATASET_YEAR:
                dates.append(dt)
            elif int(y) == 2023 and int(m) == 1 and int(d) == 1:
                dates.append(dt)  # Allow as exclusive end
        except ValueError:
            invalid_dates.append(f"{y}-{m}-{d}")

    # If the user typed two ISO dates in reverse order (e.g., "2022-05-10 to 2022-05-01"),
    # keep a flag so we can explain that we auto-corrected it later.
    try:
        if found_iso:
            ordered = re.findall(r"\b2022-\d{2}-\d{2}\b", text)
            if len(ordered) >= 2:
                d0 = datetime.strptime(ordered[0], "%Y-%m-%d")
                d1 = datetime.strptime(ordered[1], "%Y-%m-%d")
                if d0.year == DATASET_YEAR and d1.year == DATASET_YEAR and d0 > d1:
                    session_state["_dates_were_swapped"] = True
                    session_state["_swapped_from"] = ordered[0]
                    session_state["_swapped_to"] = ordered[1]
    except Exception:
        pass
    
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
    
    # 2. Whole year patterns
    whole_year = ["whole year", "all of 2022", "entire year", "full year", 
                  "all year", "the year", "year 2022"]
    if any(p in t for p in whole_year):
        return [datetime(2022, 1, 1), datetime(2023, 1, 1)]
    
    # 3. Year with breakdown context
    if "year" in t and any(w in t for w in ["monthly", "month", "breakdown", "trends", "by"]):
        if "2022" in t or not re.search(r"\b20\d{2}\b", t):
            return [datetime(2022, 1, 1), datetime(2023, 1, 1)]
    
    # 4. Quarters
    qm = Q_RE.search(t)
    if qm and ("2022" in t or not re.search(r"\b20\d{2}\b", t)):
        q = int(qm.group(1))
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 3
        start = datetime(2022, start_month, 1)
        end = datetime(2022, end_month, 1) if end_month <= 12 else datetime(2023, 1, 1)
        return [start, end]
    
    # 5. Seasons
    for season, (m1, m2) in SEASON_MAP.items():
        if season in t:
            if re.search(r"\b20(?:1\d|2[013-9])\b", t):  # Different year mentioned
                print(f"\n💡 I see '{season}' — did you mean {season} 2022?")
                return []
            return [datetime(2022, m1, 1), datetime(2022, m2, 1)]
    
    # 6. Month names (with typo tolerance)
    found_months = _find_months_in_text(t)
    if found_months:
        # Check for comparison
        comparison_words = [" vs ", " versus ", " compared to ", " compare ", " or ", " - "]
        is_comparison = any(w in t for w in comparison_words)
        
        if "2022" in t or not re.search(r"\b20\d{2}\b", t):
            if len(found_months) == 1:
                m = found_months[0]
                start = datetime(2022, m, 1)
                end = datetime(2022, m + 1, 1) if m < 12 else datetime(2023, 1, 1)
                return [start, end]
            elif len(found_months) >= 2:
                start = datetime(2022, min(found_months), 1)
                end_m = max(found_months)
                end = datetime(2022, end_m + 1, 1) if end_m < 12 else datetime(2023, 1, 1)
                return [start, end]
    
    return []
def extract_slots_from_text(user_input: str) -> None:
    """Extract all recognizable slots from user input."""
    dates = extract_dates(user_input)
    
    if len(dates) >= 1 and session_state["start_date"] is None:
        session_state["start_date"] = dates[0]
    if len(dates) >= 2 and session_state["end_date"] is None:
        session_state["end_date"] = dates[1]
    
    t = user_input.lower()
    
    # Granularity
    if session_state["granularity"] is None:
        if any(w in t for w in ["monthly", "by month", "per month"]):
            session_state["granularity"] = "monthly"
        elif any(w in t for w in ["weekly", "by week", "per week"]):
            session_state["granularity"] = "weekly"
        elif any(w in t for w in ["daily", "by day", "per day"]):
            session_state["granularity"] = "daily"
    
    # Metric
    if session_state["metric"] is None:
        if any(w in t for w in ["total", "sum", "overall"]):
            session_state["metric"] = "total"
        elif any(w in t for w in ["avg", "average", "mean", "typical"]):
            session_state["metric"] = "avg"
# =============================================================================
# SQL safety
# =============================================================================
def safe_select_only(sql: str) -> str:
    """Ensure SQL is SELECT-only."""
    low = sql.lower().strip()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only SELECT queries are allowed.")
    dangerous = ["insert", "update", "delete", "drop", "alter", "create", 
                 "truncate", "grant", "revoke", "exec", "execute"]
    for kw in dangerous:
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
        return f"""SELECT {expr} AS {label}, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY 1
ORDER BY 1;"""
    
    if intent == "sample_rows":
        # A safe sample of raw rows (SELECT-only). Keep columns minimal for UI readability.
        limit = int(session_state.get("limit") or 100)
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
    # If we are answering "best day" (cheapest), use total_amount instead of fare_amount.
    if intent == "fare_trend":
        pp = session_state.get("_postprocess") or {}
        if pp.get("type") == "best_day" and pp.get("mode") == "min_total_amount":
            col = "total_amount"
    agg = "SUM" if session_state["metric"] == "total" else "AVG"
    expr, label = time_bucket(session_state["granularity"])
    
    return f"""SELECT {expr} AS {label}, {agg}({col}) AS value
FROM taxi_trips
WHERE pickup_datetime >= '{sd}'
  AND pickup_datetime < '{ed}'
GROUP BY 1
ORDER BY 1;"""
# =============================================================================
# Smart recommendations
# =============================================================================
def recommend_granularity(start: datetime, end: datetime) -> str:
    days = (end - start).days
    if days <= 14:
        return "daily"
    elif days <= 90:
        return "weekly"
    return "monthly"
def estimate_rows(intent: str, start: datetime, end: datetime, granularity: Optional[str]) -> str:
    if intent == "vendor_inactivity":
        return "~3-5"
    if intent == "sample_rows":
        lim = session_state.get("limit") or 100
        return f"~{lim}"
    if not granularity:
        return "unknown"
    days = (end - start).days
    if granularity == "daily":
        return f"~{days}"
    elif granularity == "weekly":
        return f"~{max(1, days // 7)}"
    return f"~{max(1, days // 30)}"
def explain_sql(intent: str) -> str:
    metric = session_state.get("metric")
    explanations = {
        "trip_frequency": "Count how many taxi trips occurred in each time bucket",
        "vendor_inactivity": "Rank taxi vendors by total trips (fewest first = most inactive)",
        "fare_trend": f"Calculate {'total sum' if metric=='total' else 'average'} of fare amounts per time bucket",
        "tip_trend": f"Calculate {'total sum' if metric=='total' else 'average'} of tip amounts per time bucket",
        "sample_rows": "Show raw trip rows (limited) for quick inspection",
    }
    return explanations.get(intent, "Run analysis query")
def get_follow_up_suggestions(intent: str) -> List[str]:
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
    return suggestions.get(intent, [])
def suggest_followup(intent: str) -> None:
    items = get_follow_up_suggestions(intent)
    session_state["_last_suggestions"] = items
    session_state["_last_query_context"] = {
        "intent": intent,
        "start_date": session_state.get("start_date"),
        "end_date": session_state.get("end_date"),
        "granularity": session_state.get("granularity"),
        "metric": session_state.get("metric"),
        "query_num": session_state.get("_query_count", 0),
    }
    if items:
        print("\n💡 You might also want to:")
        for i, s in enumerate(items, 1):
            print(f"   {i}. {s}")
        print()
# =============================================================================
# Slot helpers
# =============================================================================
def missing_slots(intent: str) -> List[str]:
    req = REQUIRED_SLOTS.get(intent, [])
    return [k for k in req if session_state.get(k) is None]
def validate_dates_state() -> None:
    sd = _date_to_str(session_state["start_date"])
    ed = _date_to_str(session_state["end_date"])
    validate_range(sd, ed)
def validate_all_slots() -> bool:
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
# =============================================================================
# Input prompts
# =============================================================================
def _prompt_choice(prompt: str, choices: List[str], default: Optional[str] = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        try:
            raw = input(f"{prompt}{suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            raise
        if not raw and default:
            return default
        # UX: if user accidentally types a date when we expect a choice
        if 'granularity' in prompt.lower() and ISO_DATE_RE.search(raw):
            print("  ⚠️  That looks like a date. Please choose: daily, weekly, monthly.")
            continue
        # Try normalize for granularity
        try:
            normalized = normalize_granularity(raw)
            if normalized in choices:
                return normalized
        except ValueError:
            pass
        # Direct match
        raw_first = raw.split()[0] if raw else raw
        if raw_first in choices:
            return raw_first
        print(f"  ⚠️  Choose one: {', '.join(choices)}.")
def _prompt_yes_no(prompt: str) -> bool:
    """Yes/No prompt with friendly synonyms.
    Accepts: yes/y/approve/run, no/n/deny/cancel/stop.
    """
    while True:
        try:
            raw = input(f"{prompt} (yes/no): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            raise
        if raw in ("yes", "y", "approve", "run", "ok", "okay"):
            return True
        if raw in ("no", "n", "deny", "cancel", "stop", "abort", "nope"):
            return False
        print("  ⚠️  Please type yes or no (or 'deny' to cancel).")
def _prompt_date(field: str, example: str) -> datetime:
    while True:
        try:
            raw = input(f"{field} (YYYY-MM-DD, 2022 only) e.g. {example}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            raise
        if not raw:
            continue
        try:
            validate_date(raw)
            return _parse_date(raw)
        except Exception as e:
            print(f"  ⚠️  {e}")
# =============================================================================
# Meta/guidance detection
# =============================================================================
SUMMARY_RE = re.compile(r"\b(summar|insight|overview|what.?happened|tell me about)\b", re.I)
HELPISH_RE = re.compile(r"\b(help|what can i|how can you|who are you|your name)\b", re.I)
def _is_summaryish(text: str) -> bool:
    return bool(SUMMARY_RE.search(text))
def _has_specific_topic(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ["fare", "fares", "tip", "tips", "trip", "trips", "vendor", "vendors"])
def _has_time_context(text: str) -> bool:
    t = text.lower()
    if any(s in t for s in SEASON_MAP.keys()):
        return True
    if Q_RE.search(t):
        return True
    if ISO_DATE_RE.search(t):
        return True
    if _find_months_in_text(t):
        return True
    return False
def _needs_summary_wizard(text: str) -> bool:
    t = text.lower()
    if _is_summaryish(t) and _has_time_context(t) and not _has_specific_topic(t):
        return True
    if _is_summaryish(t) and not _has_specific_topic(t) and not _has_time_context(t):
        return True
    return False
def _handle_summary_wizard() -> Optional[str]:
    print("\n🧾 Summary mode — I can summarize a period, but I need 2 things:")
    print("1) Topic: trips / fares / tips / vendors")
    print("2) Period: e.g., summer 2022, Q2 2022, November 2022\n")
    
    topic = _prompt_choice("Topic (trips/fares/tips/vendors)", 
                          ["trips", "fares", "tips", "vendors"], default="trips")
    period = input("Period (example: summer 2022): ").strip()
    if not period:
        print("  ⚠️  Please provide a period.\n")
        return None
    
    if topic == "trips":
        return f"show trips in {period} by monthly"
    if topic == "vendors":
        return f"which vendors were inactive in {period}"
    
    print("\nMetric controls how we aggregate money:")
    print("  - avg   = average per trip")
    print("  - total = total sum in the period")
    metric = _prompt_choice("Metric (avg/total)", ["avg", "total"], default="avg")
    
    if topic == "fares":
        return f"show {metric} fares in {period} by monthly"
    return f"show {metric} tips in {period} by monthly"
def contextual_help(user_input: str) -> None:
    t = user_input.lower()
    if "date" in t or "when" in t:
        print("\n📅 Date format: YYYY-MM-DD (example: 2022-06-15)")
        print("Shortcuts: 'summer 2022', 'Q2 2022', 'November 2022'\n")
    elif "granularity" in t:
        print("\n📊 Granularity options: daily, weekly, monthly\n")
    elif "metric" in t:
        print("\n💰 Metric options: avg (average per trip), total (sum)\n")
    else:
        print("\n" + HELP_TEXT + "\n")
# =============================================================================
# Numbered follow-up handling
# =============================================================================
def _handle_numbered_followup(num_str: str) -> Optional[str]:
    try:
        num = int(num_str)
    except ValueError:
        return None
    
    suggestions = session_state.get("_last_suggestions", [])
    context = session_state.get("_last_query_context")
    current_query = session_state.get("_query_count", 0)
    
    # Check if context exists and is fresh
    if not suggestions or not context:
        print("\n❓ No previous query to follow up on.")
        print("Try asking a question first, like: 'show trips in January 2022 by week'\n")
        return ""
    
    # Check if context is stale (more than 1 query ago)
    context_query = context.get("query_num", 0)
    if current_query - context_query > 1:
        print("\n❓ The previous suggestions are no longer valid.")
        print("Please ask a new question or run a query first.\n")
        return ""
    
    if num < 1 or num > len(suggestions):
        print(f"  ⚠️  Please choose a number between 1 and {len(suggestions)}.\n")
        return ""
    
    suggestion = suggestions[num - 1]
    last_intent = context.get("intent")
    sd, ed = context.get("start_date"), context.get("end_date")
    gran = context.get("granularity", "monthly")
    
    # Handle each suggestion type
    if "Compare this to another period" in suggestion:
        print("\n📅 To compare periods, specify a new date range.")
        print("Example: 'show trips in Q1 2022 by month'\n")
        return ""
    
    if "vendors" in suggestion.lower() and last_intent == "trip_frequency":
        if sd and ed:
            return f"show inactive vendors from {_date_to_str(sd)} to {_date_to_str(ed)}"
    
    if "fare" in suggestion.lower():
        if sd and ed:
            return f"show avg fares from {_date_to_str(sd)} to {_date_to_str(ed)} by {gran}"
    
    if "tip" in suggestion.lower():
        if sd and ed:
            return f"show avg tips from {_date_to_str(sd)} to {_date_to_str(ed)} by {gran}"
    
    if "trip" in suggestion.lower() and last_intent == "vendor_inactivity":
        if sd and ed:
            return f"show trips from {_date_to_str(sd)} to {_date_to_str(ed)} by monthly"
    
    if "Compare vendor" in suggestion:
        print("\n📊 To compare vendors across quarters, try:")
        print("   'show inactive vendors in Q1 2022'\n")
        return ""
    
    print(f"\n💡 Selected: {suggestion}")
    print("Please rephrase this as a question.\n")
    return ""
# =============================================================================
# Explain last result (UX)
# =============================================================================
def explain_last_result(style: str = "simple") -> None:
    df = session_state.get("_last_df")
    ctx = session_state.get("_last_query_context") or {}
    if df is None or getattr(df, "empty", True):
        print("\n❓ I don't have a recent result to explain yet.")
        print("Run a query first, then ask: 'explain the result'.\n")
        return
    intent = ctx.get("intent")
    # If intent context is missing, infer from the last dataframe columns for a better UX.
    if not intent:
        cols = [c.lower() for c in getattr(df, "columns", [])]
        if "trips" in cols:
            intent = "trip_frequency"
        elif "vendor_id" in cols and "trips" in cols:
            intent = "vendor_inactivity"
        elif "tip_amount" in cols or ("value" in cols and (ctx.get("topic","") or "").startswith("tip")):
            intent = "tip_trend"
        elif "fare_amount" in cols or "value" in cols:
            intent = "fare_trend"
    sd = ctx.get("start_date")
    ed = ctx.get("end_date")
    gran = ctx.get("granularity")
    metric = ctx.get("metric")
    period = ""
    try:
        if sd and ed:
            period = f" ({_date_to_str(sd)} to {_date_to_str(ed)}, end exclusive)"
    except Exception:
        period = ""
    print("\n🧾 Explanation" + period)
    if style == "newbie":
        print("I'll keep it simple and focus on what the numbers mean.\n")
    try:
        # Common cases
        if intent == "trip_frequency" and len(df.columns) >= 2:
            xcol, ycol = df.columns[0], df.columns[1]
            y = df[ycol]
            print(f"- Each row is one {gran or 'time'} bucket, and `{ycol}` is the number of trips in that bucket.")
            print(f"- In this result, trips range from {int(y.min())} to {int(y.max())} per {xcol}.")
            max_row = df.loc[y.idxmax()]
            min_row = df.loc[y.idxmin()]
            print(f"- Highest day: {max_row[xcol]} with {int(max_row[ycol])} trips.")
            print(f"- Lowest day:  {min_row[xcol]} with {int(min_row[ycol])} trips.")
            print("\nNext useful step: compare to another period (e.g., March vs April) to confirm it's truly 'low'.")
            print("Try: 'compare April to March 2022 by week'\n")
            return
        if intent in ("fare_trend", "tip_trend") and "value" in df.columns:
            y = df["value"]
            label = "fares" if intent == "fare_trend" else "tips"
            agg = "total" if metric == "total" else "average"
            print(f"- Each row is one {gran or 'time'} bucket; `value` is the {agg} {label} for that bucket.")
            print(f"- Values range from {float(y.min()):.2f} to {float(y.max()):.2f}.")
            print("\nNext useful step: compare against trip counts (are changes due to volume or price?).\n")
            return
        if intent == "vendor_inactivity" and "trips" in df.columns:
            print("- Each row is a vendor, and `trips` is how many trips they had in the period.")
            print("- Vendors are sorted from fewest trips to most trips (fewest = most inactive).\n")
            return
        if intent == "sample_rows":
            print("- This is a small sample of raw trips (not aggregated).")
            print("- Use it to sanity-check columns, values, and data quality.\n")
            return
    except Exception:
        pass
    # Generic fallback
    print("- Here's what I did: I ran a safe SQL query and returned a table.")
    print("- If you tell me what decision you're trying to make, I can translate the numbers into a conclusion.\n")
# =============================================================================
# Vague time handling
# =============================================================================
def _is_vague_time_only(text: str) -> bool:
    t = text.lower()
    vague = ["last month", "this month", "yesterday", "today", "last week", 
             "this week", "recently", "lately"]
    return any(v in t for v in vague) and not _has_time_context(t)
def _handle_vague_time_reference(user_input: str) -> Optional[str]:
    t = user_input.lower()
    if not _is_vague_time_only(t):
        return None
    
    patterns = [
        ("last month", "❓ 'Last month' is ambiguous for this 2022 dataset."),
        ("this month", "❓ 'This month' is ambiguous for this 2022 dataset."),
        ("yesterday", "❓ 'Yesterday' is ambiguous for this 2022 dataset."),
        ("today", "❓ 'Today' is ambiguous for this 2022 dataset."),
        ("last week", "❓ 'Last week' is ambiguous for this 2022 dataset."),
        ("this week", "❓ 'This week' is ambiguous for this 2022 dataset."),
        ("recently", "❓ 'Recently' is ambiguous for this 2022 dataset."),
        ("lately", "❓ 'Lately' is ambiguous for this 2022 dataset."),
    ]
    
    for pattern, msg in patterns:
        if pattern in t:
            print(f"\n{msg}")
            print("Try: 'show trips in November 2022' or 'fares in Q4 2022'\n")
            return ""
    return None
# =============================================================================
# Main meta/guidance handler
# =============================================================================
def _handle_meta_or_guidance(user_input: str) -> Optional[str]:
    t = user_input.strip()
    t_lower = t.lower()

    # If the user types a bare yes/no outside of a prompt, guide them back.
    if t_lower in {"y", "yes", "yeah", "yep", "ok", "okay", "sure", "n", "no", "nope"}:
        return "I didn’t ask a yes/no question yet 🙂\nTry asking something like: 'show trips in April 2022 by week' or type 'help'."
    
    # Numbered follow-up
    if t.isdigit():
        return _handle_numbered_followup(t)
    # Explain last result (friendly UX)
    if any(k in t_lower for k in ["explain the result", "explain this", "explain it", "like i'm new", "like i am new", "eli5"]):
        style = "newbie" if ("new" in t_lower or "eli5" in t_lower) else "simple"
        explain_last_result(style=style)
        return ""
    # Quick revision: user says "use 2022-... to 2022-... instead"
    # Treat as a continuation by rewriting into a supported query.
    if t_lower.startswith("use ") and ("2022-" in t_lower) and (" to " in t_lower or "-" in t_lower):
        dates = re.findall(r"\b2022-\d{2}-\d{2}\b", t_lower)
        if len(dates) >= 2:
            d1, d2 = dates[0], dates[1]
            # Re-route into a normal supported query so the router understands it.
            return f"show trips from {d1} to {d2} by week"
    # Follow-up: sample rows (use previous period if available)
    if any(k in t_lower for k in ["sample", "show me a sample", "show a sample", "sample of"]) and any(k in t_lower for k in ["row", "rows", "record", "records"]):
        n = 100
        mnum = re.search(r"\b(\d{1,4})\b", t_lower)
        if mnum:
            n = max(1, min(int(mnum.group(1)), 1000))
        # Prefer the last executed range; fall back to the current session range; then fall back to a small default window.
        ctx = session_state.get("_last_query_context") or {}
        sd = ctx.get("start_date") or session_state.get("start_date")
        ed = ctx.get("end_date") or session_state.get("end_date")
        if sd and ed:
            return f"show a sample of {n} rows from {_date_to_str(sd)} to {_date_to_str(ed)}"
        return f"show a sample of {n} rows from 2022-01-01 to 2022-01-08"
    # Follow-up: compare to another month (use previous topic + granularity)
    if any(k in t_lower for k in ["compare", "versus", "vs"]) and _find_months_in_text(t_lower):
        ctx = session_state.get("_last_query_context") or {}
        topic_intent = ctx.get("intent") or "trip_frequency"
        gran = ctx.get("granularity") or "weekly"
        metric = ctx.get("metric")
        if topic_intent == "fare_trend":
            metric_txt = "avg" if metric != "total" else "total"
            return f"show {metric_txt} fares in {t_lower} by {gran}"
        if topic_intent == "tip_trend":
            metric_txt = "avg" if metric != "total" else "total"
            return f"show {metric_txt} tips in {t_lower} by {gran}"
        return f"show trips in {t_lower} by {gran}"
    # Question: best day to travel (guided)
    if "best day" in t_lower and any(k in t_lower for k in ["travel", "ride", "go"]):
        print("\n❓ Quick clarification for 'best day':")
        print("What does *best* mean for you?")
        print("  1) Cheapest (lowest average total amount)")
        print("  2) Most available (highest trip count)")
        try:
            choice = input("Choose 1/2 [1]: ").strip() or "1"
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return ""
        period = input("Which period? (example: April 2022): ").strip() or "April 2022"
        if choice == "2":
            session_state["_postprocess"] = {"type": "best_day", "mode": "max_trips"}
            return f"show trips in {period} by daily"
        session_state["_postprocess"] = {"type": "best_day", "mode": "min_total_amount"}
        return f"show avg fares in {period} by daily"
    # Help command
    if t_lower == "help":
        contextual_help(user_input)
        return ""
    
    # Help-ish questions
    if HELPISH_RE.search(t_lower):
        print("\nI can help with NYC taxi data in 2022.")
        print("Topics: trips, fares, tips, vendors")
        print("Type 'help' for examples.\n")
        return ""
    
    # Greetings
    greetings = ["hey", "hi ", "hi,", "hello", "i'm new", "what can you do", 
                 "good morning", "good afternoon", "good evening"]
    if any(g in t_lower for g in greetings):
        print("\nI can help with NYC taxi data in 2022.")
        print("Topics: trips, fares, tips, vendors")
        print("Type 'help' for examples.\n")
        return ""
    
    # Vague time references
    vague = _handle_vague_time_reference(user_input)
    if vague is not None:
        return vague
    
    # Unsupported queries (check BEFORE summary wizard)
    unsupported = detect_unsupported_query(user_input)
    if unsupported:
        print(f"\n{unsupported}")
        print("\nTry: 'show trips in summer 2022 by week'\n")
        return ""
    
    # Summary wizard
    if _needs_summary_wizard(t_lower):
        rewritten = _handle_summary_wizard()
        return rewritten if rewritten else ""
    
    return None
# =============================================================================
# Busier clarification
# =============================================================================
def _clarify_busier() -> Tuple[str, bool]:
    print("\n❓ Quick clarification:")
    print("When you say *busier*, do you mean:")
    print("  1) Number of trips (more rides = busier)")
    print("  2) Total revenue (more money = busier)")
    print("  3) Average fare per trip")
    while True:
        try:
            raw = input("Choose 1/2/3: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return ("trip_frequency", False)
        if raw == "1":
            return ("trip_frequency", True)
        if raw == "2":
            session_state["metric"] = "total"
            return ("fare_trend", True)
        if raw == "3":
            session_state["metric"] = "avg"
            return ("fare_trend", True)
        print("  ⚠️  Choose 1, 2, or 3.")
def _needs_busier_clarification(user_input: str) -> bool:
    t = user_input.lower()
    busy = ["busier", "busy", "more active", "less active", "quieter", "slower"]
    comparison = ["vs", "versus", "compared", "than", "or"]
    return any(b in t for b in busy) and any(c in t for c in comparison)
# =============================================================================
# Multi-topic handler
# =============================================================================
def _handle_multi_topic(topics: List[str]) -> str:
    print(f"\n❓ I noticed you mentioned multiple topics: {', '.join(topics)}")
    print("I can only analyze one at a time. Which would you like?\n")
    for i, topic in enumerate(topics, 1):
        print(f"  {i}) {topic}")
    while True:
        try:
            raw = input(f"Choose 1-{len(topics)}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            return topics[0]
        try:
            num = int(raw)
            if 1 <= num <= len(topics):
                return topics[num - 1]
        except ValueError:
            pass
        print(f"  ⚠️  Choose 1-{len(topics)}.")
# =============================================================================
# Main agent loop
# =============================================================================
def run_agent():
    global session_state
    
    print("\n" + INTRO + "\n")
    
    # Show mode
    if os.getenv("OPENAI_API_KEY"):
        if MODEL is None:
            print("⚠️  OPENAI_API_KEY set but client unavailable. Using deterministic mode.\n")
        else:
            print("✅ ChatGPT routing is enabled (OpenAI).\n")
    else:
        print("ℹ️  ChatGPT routing OFF. Using deterministic mode.\n")
    
    print('👋 First time here? Try: "show trips in January 2022 by week"\n')
    
    while True:
        try:
            q = input("Ask a question: ").strip()
            # Per-turn locals
            sql = None
            df = None
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!\n")
            break
        
        if not q:
            continue

        # Remember if user asked for a single day ("trips on YYYY-MM-DD")
        # Helps us keep date prompts sensible after correcting invalid dates.
        session_state["_single_day_request"] = bool(re.search(r"\b(on|for)\s+\d{4}-\d{2}-\d{2}\b", q.lower()) and " to " not in q.lower())
        
        if q.lower() in ("exit", "quit", "bye", "q"):
            print("\n👋 Goodbye!\n")
            break
        
        if q.lower() == "reset":
            session_state = reset_session()
            print("Session reset.\n")
            continue
        
        # Security: SQL injection
        if detect_sql_injection(q):
            print("\n🚫 That looks like a SQL injection attempt.")
            print("I only run safe, pre-built SELECT queries.\n")
            continue
        
        # Meta/guidance handling
        meta = _handle_meta_or_guidance(q)
        if meta is not None:
            if meta == "":
                continue
            q = meta
        
        # Multi-topic detection
        multi = detect_multi_topic(q)
        if multi:
            chosen = _handle_multi_topic(multi)
            # Simplify query to chosen topic
            q = re.sub(r'\b(trip|trips|ride|rides|fare|fares|tip|tips|vendor|vendors)\b', 
                      '', q, flags=re.I)
            q = q.strip() + f" {chosen}"
        
        # Preserve context for follow-ups
        last_suggestions = session_state.get("_last_suggestions", [])
        last_context = session_state.get("_last_query_context")
        query_count = session_state.get("_query_count", 0)
        
        session_state = reset_session()
        session_state["_last_suggestions"] = last_suggestions
        session_state["_last_query_context"] = last_context
        session_state["_query_count"] = query_count
        
        # Busier clarification
        needs_busier = _needs_busier_clarification(q)
        
        # Semantic rewrite
        rewrite = semantic_rewrite(q)
        rewritten = (rewrite.get("rewritten") or q).strip()
        
        # Apply LLM hints
        if rewrite.get("granularity_hint") in ("daily", "weekly", "monthly"):
            session_state["granularity"] = rewrite["granularity_hint"]
        if rewrite.get("metric_hint") in ("avg", "total"):
            session_state["metric"] = rewrite["metric_hint"]
        
        # Extract slots
        extract_slots_from_text(rewritten)

        # If we auto-corrected reversed dates, make it explicit to the user (helps trust).
        if session_state.get("_dates_were_swapped"):
            f = session_state.get("_swapped_from")
            tto = session_state.get("_swapped_to")
            # Only show once per correction
            session_state["_dates_were_swapped"] = False
            if f and tto:
                print(f"\n🔁 I noticed the dates were reversed ({f} → {tto}). I’ll use {tto} to {f} instead.\n")
        
        # Handle invalid dates
        if session_state.get("_saw_invalid_iso_date"):
            print("  Let's enter valid dates.\n")
            # If the user asked for a single day (e.g., "trips on ..."), make it easy:
            # ask for one start_date and auto-set end_date to next day.
            single_day_hint = (" on " in q.lower()) and (" to " not in q.lower()) and ("from" not in q.lower())
            session_state["start_date"] = None
            session_state["end_date"] = None
            if single_day_hint:
                sd = _prompt_date("start_date", "2022-06-15")
                session_state["start_date"] = sd
                session_state["end_date"] = sd + timedelta(days=1)
                print(f"\n💡 I’ll treat this as a single-day range: {_date_to_str(sd)} only (end_date is exclusive).\n")
            session_state["_saw_invalid_iso_date"] = False
            session_state["_invalid_dates"] = []
        
        # Route
        route = ask_gemini_router(rewritten)
        if not route.get("dataset_match", True):
            print("\n❌ Out of scope (NYC Yellow Taxi 2022 only).")
            print("Try: trips, fares, tips, or vendors in 2022.\n")
            continue
        
        intent = route.get("intent", "unknown")
        
        # If user asked for a sample but didn't specify dates, reuse the last executed range if available.
        if intent == "sample_rows":
            if session_state.get("start_date") is None or session_state.get("end_date") is None:
                ctx = session_state.get("_last_query_context") or {}
                if ctx.get("start_date") and ctx.get("end_date"):
                    session_state["start_date"] = ctx["start_date"]
                    session_state["end_date"] = ctx["end_date"]

        # Busier handling
        if needs_busier:
            intent, ok = _clarify_busier()
            if not ok:
                continue
        elif intent not in SUPPORTED_INTENTS:
            print("\n❓ I can help with: trips, fares, tips, or vendors.")
            print('Try: "show trips in January 2022 by week"\n')
            continue
        
        session_state["intent"] = intent
        
        # Fill missing slots
        for slot in missing_slots(intent):
            if slot == "start_date":
                session_state["start_date"] = _prompt_date("start_date", "2022-06-01")
            elif slot == "end_date":
                session_state["end_date"] = _prompt_date("end_date", "2022-09-01")
            elif slot == "granularity":
                if session_state["start_date"] and session_state["end_date"]:
                    suggestion = recommend_granularity(
                        session_state["start_date"], session_state["end_date"])
                    days = (session_state["end_date"] - session_state["start_date"]).days
                    print(f"\n💡 For a {days}-day range, '{suggestion}' often works well.")
                else:
                    suggestion = "weekly"
                session_state["granularity"] = _prompt_choice(
                    "granularity (daily/weekly/monthly)",
                    ["daily", "weekly", "monthly"],
                    default=suggestion)
            elif slot == "metric":
                print("\nMetric controls how we aggregate money:")
                print("  - avg   = average per trip")
                print("  - total = total sum in the period")
                session_state["metric"] = _prompt_choice(
                    "metric (avg/total)", ["avg", "total"], default="avg")


        # Optional slot for sampling
        if intent == "sample_rows" and not session_state.get("limit"):
            while True:
                try:
                    raw_lim = input("limit (rows to show) [100]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n")
                    raise
                if not raw_lim:
                    session_state["limit"] = 100
                    break
                if raw_lim.isdigit():
                    lim = int(raw_lim)
                    if 1 <= lim <= 1000:
                        session_state["limit"] = lim
                        break
                print("  ⚠️  Enter a number between 1 and 1000.")

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
        
        # Final validation
        if not validate_all_slots():
            print("Cannot proceed. Try again.\n")
            continue
        

        # Warn if granularity seems too coarse for a short range
        if intent in ("trip_frequency", "fare_trend", "tip_trend") and session_state.get("granularity"):
            days = (session_state["end_date"] - session_state["start_date"]).days
            if days <= 7 and session_state["granularity"] != "daily":
                print(f"\n💡 Note: Your range is only {days} day(s).")
                print("   Daily usually makes more sense than weekly/monthly for such a short window.")
                if not _prompt_yes_no("Continue with this granularity?"):
                    session_state["granularity"] = "daily"

        # Warn about large daily queries
        if intent in ("trip_frequency", "fare_trend", "tip_trend") and session_state.get("granularity") == "daily":
            days = (session_state["end_date"] - session_state["start_date"]).days
            if days > 90:
                print(f"\n⚠️  Daily granularity for {days} days = many rows.")
                print("   Consider 'weekly' or 'monthly' for clearer trends.")
                if not _prompt_yes_no("Continue with daily?"):
                    session_state["granularity"] = _prompt_choice(
                        "Choose granularity", ["weekly", "monthly"], default="weekly")


        # Build and show plan
        sd = _date_to_str(session_state["start_date"])
        ed = _date_to_str(session_state["end_date"])
        gran = session_state.get("granularity")
        metric = session_state.get("metric")
        
        task_names = {
            "trip_frequency": "Count trips over time",
            "vendor_inactivity": "Rank vendors by trip count (lowest = most inactive)",
            "fare_trend": f"{'Sum' if metric=='total' else 'Average'} fares over time",
            "tip_trend": f"{'Sum' if metric=='total' else 'Average'} tips over time",
            "sample_rows": "Show a safe sample of raw trip rows",
        }
        
        print("\n" + "="*60)
        print("🧠 EXECUTION PLAN")
        print("="*60)
        print(f"📌 Task: {task_names[intent]}")
        print(f"📅 Period: {sd} to {ed} (exclusive)")
        if gran:
            print(f"⏱️  Granularity: {gran}")
        if metric and intent in ("fare_trend", "tip_trend"):
            print(f"📊 Metric: {metric}")
        rows = estimate_rows(intent, session_state["start_date"], 
                            session_state["end_date"], gran)
        print(f"💾 Expected output: {rows} rows")
        print("="*60 + "\n")
        
        if not _prompt_yes_no("Does this look correct?"):
            print("Cancelled.\n")
            continue
        
        # Show SQL explanation and query
        print(f"\n📊 What this query does:")
        print(f"   {explain_sql(intent)}\n")
        
        sql = safe_select_only(build_sql(intent))
        print("SQL:")
        print(sql)
        print()
        
        if not _prompt_yes_no("Run query?"):
            print("Cancelled.\n")
            continue
        
        # Execute
        print("⏳ Running query...")
        try:
            df = execute_sql_query(sql)
            print("✅ Query complete!\n")
        except Exception as e:
            print(f"\n❌ Query failed: {e}")
            print("This might be a bug — please report it.\n")
            continue
        
        # Handle results
        if len(df) == 0:
            print("⚠️  Query returned 0 rows.")
            print("Possible reasons:")
            print("  • Date range has no data")
            print("  • Try expanding the date range\n")
            continue
        
        # Show results
        print(df.head(20))
        print(f"\nDone. Returned {len(df)} rows.\n")
        # Save last result for follow-ups / explanation
        if sql is not None:
            session_state["_last_sql"] = sql
        session_state["_last_df"] = df
        session_state["_last_df_rows"] = len(df)
        session_state["_last_user_question"] = q
        # Update follow-up context (used by "compare", "sample", "explain")
        try:
            session_state["_query_count"] = int(session_state.get("_query_count", 0)) + 1
        except Exception:
            session_state["_query_count"] = 1
        try:
            # Ensure context exists even if suggestions are not printed
            session_state["_last_query_context"] = {
                "intent": session_state.get("intent"),
                "start_date": session_state.get("start_date"),
                "end_date": session_state.get("end_date"),
                "granularity": session_state.get("granularity"),
                "metric": session_state.get("metric"),
            }
        except Exception:
            pass
        try:
            suggest_followup(session_state.get("intent") or "trip_frequency")
        except Exception:
            pass
        # Post-processing hooks (e.g., best day)
        pp = session_state.get("_postprocess") or {}
        if pp.get("type") == "best_day":
            try:
                if pp.get("mode") == "max_trips" and len(df.columns) >= 2:
                    ycol = df.columns[1]
                    best = df.loc[df[ycol].idxmax()]
                    print("🏆 Best day (most available):")
                    print(f"   {best[df.columns[0]]} with {int(best[ycol])} trips\n")
                elif pp.get("mode") == "min_total_amount" and "value" in df.columns:
                    best = df.loc[df["value"].idxmin()]
                    print("🏆 Best day (cheapest by avg total amount):")
                    print(f"   {best[df.columns[0]]} with avg total ${float(best['value']):.2f}\n")
            except Exception:
                pass
            finally:
                # Clear hook after use
                session_state["_postprocess"] = None

                # Update query count and suggest follow-ups
                session_state["_query_count"] = query_count + 1
                suggest_followup(intent)
if __name__ == "__main__":
    run_agent()