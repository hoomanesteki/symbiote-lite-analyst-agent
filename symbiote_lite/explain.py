from __future__ import annotations

from typing import Any, Dict, List, Optional

from .dates import DATASET_YEAR
from .slots import recommend_granularity

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

def explain_sql(state: Dict[str, Any], intent: str) -> str:
    metric = state.get("metric")
    explanations = {
        "trip_frequency": "Count how many taxi trips occurred in each time bucket",
        "vendor_inactivity": "Rank taxi vendors by total trips (fewest first = most inactive)",
        "fare_trend": f"Calculate {'total sum' if metric=='total' else 'average'} of fare amounts per time bucket",
        "tip_trend": f"Calculate {'total sum' if metric=='total' else 'average'} of tip amounts per time bucket",
        "sample_rows": "Show raw trip rows (limited) for quick inspection",
    }
    return explanations.get(intent, "Run analysis query")

def estimate_rows(state: Dict[str, Any], intent: str) -> str:
    if intent == "vendor_inactivity":
        return "~3-5"
    if intent == "sample_rows":
        lim = state.get("limit") or 100
        return f"~{lim}"
    granularity = state.get("granularity")
    if not granularity:
        return "unknown"
    days = (state["end_date"] - state["start_date"]).days
    if granularity == "daily":
        return f"~{days}"
    if granularity == "weekly":
        return f"~{max(1, days // 7)}"
    return f"~{max(1, days // 30)}"

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

def suggest_followup(state: Dict[str, Any], intent: str) -> None:
    items = get_follow_up_suggestions(intent)
    state["_last_suggestions"] = items
    state["_last_query_context"] = {
        "intent": intent,
        "start_date": state.get("start_date"),
        "end_date": state.get("end_date"),
        "granularity": state.get("granularity"),
        "metric": state.get("metric"),
        "query_num": state.get("_query_count", 0),
    }
    if items:
        print("\n💡 You might also want to:")
        for i, s in enumerate(items, 1):
            print(f"   {i}. {s}")
        print()

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

def explain_last_result(state: Dict[str, Any], style: str = "simple") -> None:
    df = state.get("_last_df")
    ctx = state.get("_last_query_context") or {}
    if df is None or getattr(df, "empty", True):
        print("\n❓ I don't have a recent result to explain yet.")
        print("Run a query first, then ask: 'explain the result'.\n")
        return

    intent = ctx.get("intent")
    if not intent:
        cols = [c.lower() for c in getattr(df, "columns", [])]
        if "trips" in cols:
            intent = "trip_frequency"
        elif "vendor_id" in cols and "trips" in cols:
            intent = "vendor_inactivity"
        elif "value" in cols:
            intent = "fare_trend"

    sd = ctx.get("start_date")
    ed = ctx.get("end_date")
    gran = ctx.get("granularity")
    metric = ctx.get("metric")

    period = ""
    try:
        if sd and ed:
            period = f" ({sd.strftime('%Y-%m-%d')} to {ed.strftime('%Y-%m-%d')}, end exclusive)"
    except Exception:
        period = ""

    print("\n🧾 Explanation" + period)
    if style == "newbie":
        print("I'll keep it simple and focus on what the numbers mean.\n")

    try:
        if intent == "trip_frequency" and len(df.columns) >= 2:
            xcol, ycol = df.columns[0], df.columns[1]
            y = df[ycol]
            print(f"- Each row is one {gran or 'time'} bucket, and `{ycol}` is the number of trips in that bucket.")
            print(f"- Trips range from {int(y.min())} to {int(y.max())} per {xcol}.")
            max_row = df.loc[y.idxmax()]
            min_row = df.loc[y.idxmin()]
            print(f"- Highest: {max_row[xcol]} with {int(max_row[ycol])} trips.")
            print(f"- Lowest:  {min_row[xcol]} with {int(min_row[ycol])} trips.\n")
            return

        if intent in ("fare_trend", "tip_trend") and "value" in df.columns:
            y = df["value"]
            label = "fares" if intent == "fare_trend" else "tips"
            agg = "total" if metric == "total" else "average"
            print(f"- Each row is one {gran or 'time'} bucket; `value` is the {agg} {label} for that bucket.")
            print(f"- Values range from {float(y.min()):.2f} to {float(y.max()):.2f}.\n")
            return

        if intent == "vendor_inactivity" and "trips" in df.columns:
            print("- Each row is a vendor, and `trips` is how many trips they had in the period.")
            print("- Sorted from fewest trips to most trips (fewest = most inactive).\n")
            return

        if intent == "sample_rows":
            print("- This is a small sample of raw trips (not aggregated).\n")
            return
    except Exception:
        pass

    print("- I ran a safe SQL query and returned a table.")
    print("- Tell me what decision you're trying to make and I'll translate the numbers.\n")
