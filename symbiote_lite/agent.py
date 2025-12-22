from __future__ import annotations

import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Load .env from project root
ROOT = Path(__file__).resolve().parents[1]
if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

from .router import configure_model, ask_router, semantic_rewrite
from .dates import ISO_DATE_RE
from .slots import (
    reset_session, missing_slots, extract_slots_from_text,
    validate_all_slots, validate_dates_state, normalize_granularity, normalize_metric,
    SUPPORTED_INTENTS,
)
from .sql.safety import detect_sql_injection, safe_select_only
from .sql.builder import build_sql
# ============================================================
# MCP INTEGRATION: Import the tool executor instead of direct SQL
# ============================================================
from .tools.executor import DirectToolExecutor

from .explain import (
    INTRO, contextual_help, recommend_granularity, estimate_rows,
    explain_sql, suggest_followup, explain_last_result,
)

# ============================================================
# MCP INTEGRATION: Create a single tool executor instance
# All SQL execution goes through this boundary
# ============================================================
_tool_executor = DirectToolExecutor()


# ----------------------------
# Unsupported query patterns
# ----------------------------
UNSUPPORTED_PATTERNS = [
    (r"\b(weekend|weekday|saturday|sunday|weekends|weekdays)\s.*(busy|busier|more|less|compar|vs|than)",
     "⚠️  Weekend vs weekday breakdown isn't supported yet.\nI can show daily data or weekly/monthly aggregation."),
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
    t = (user_input or "").lower()
    for pattern, explanation in UNSUPPORTED_PATTERNS:
        if re.search(pattern, t):
            return explanation
    return None

def detect_multi_topic(user_input: str) -> Optional[List[str]]:
    t = (user_input or "").lower()
    topics_found: List[str] = []
    if " and " in t or ", " in t:
        if any(w in t for w in ["trip", "trips", "ride", "rides"]):
            topics_found.append("trips")
        if any(w in t for w in ["fare", "fares", "revenue", "money", "price"]):
            topics_found.append("fares")
        if any(w in t for w in ["tip", "tips", "tipping"]):
            topics_found.append("tips")
        if any(w in t for w in ["vendor", "vendors", "company", "companies"]):
            topics_found.append("vendors")
    return topics_found if len(topics_found) >= 2 else None

SUMMARY_RE = re.compile(r"\b(summar|insight|overview|what.?happened|tell me about)\b", re.I)
HELPISH_RE = re.compile(r"\b(help|what can i|how can you|who are you|your name)\b", re.I)

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
        if 'granularity' in prompt.lower() and ISO_DATE_RE.search(raw):
            print("  ⚠️  That looks like a date. Please choose: daily, weekly, monthly.")
            continue
        try:
            normalized = normalize_granularity(raw)
            if normalized in choices:
                return normalized
        except ValueError:
            pass
        raw_first = raw.split()[0] if raw else raw
        if raw_first in choices:
            return raw_first
        print(f"  ⚠️  Choose one: {', '.join(choices)}.")

def _prompt_yes_no(prompt: str) -> bool:
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

def _prompt_date(field: str, example: str):
    from .dates import validate_date as _validate_date
    from .dates import _parse_date as _parse_date  # type: ignore
    while True:
        try:
            raw = input(f"{field} (YYYY-MM-DD, 2022 only) e.g. {example}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            raise
        if not raw:
            continue
        try:
            _validate_date(raw)
            return _parse_date(raw)
        except Exception as e:
            print(f"  ⚠️  {e}")

def _needs_busier_clarification(user_input: str) -> bool:
    t = user_input.lower()
    busy = ["busier", "busy", "more active", "less active", "quieter", "slower"]
    comparison = ["vs", "versus", "compared", "than", "or"]
    return any(b in t for b in busy) and any(c in t for c in comparison)

def _clarify_busier(state: Dict[str, Any]) -> Tuple[str, bool]:
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
            state["metric"] = "total"
            return ("fare_trend", True)
        if raw == "3":
            state["metric"] = "avg"
            return ("fare_trend", True)
        print("  ⚠️  Choose 1, 2, or 3.")


# ============================================================
# MCP INTEGRATION: Helper function to execute SQL via MCP boundary
# ============================================================
def _execute_via_mcp(sql: str):
    """
    Execute SQL through the MCP tool boundary.
    
    This is the KEY CHANGE that makes the agent MCP-compliant.
    The agent does NOT directly call execute_sql_query().
    Instead, it goes through the DirectToolExecutor.
    """
    result = _tool_executor.execute_sql(sql)
    if not result.get("success"):
        raise RuntimeError("MCP tool execution failed")
    return result.get("dataframe")


def run_agent():
    model = configure_model()
    state: Dict[str, Any] = reset_session()

    print("\n" + INTRO + "\n")

    if os.getenv("OPENAI_API_KEY"):
        if model is None:
            print("⚠️  OPENAI_API_KEY set but client unavailable. Using deterministic mode.\n")
        else:
            print("✅ ChatGPT routing is enabled (OpenAI).\n")
    else:
        print("ℹ️  ChatGPT routing OFF. Using deterministic mode.\n")

    # ============================================================
    # MCP INTEGRATION: Show that execution goes through MCP
    # ============================================================
    print("🔗 MCP Mode: All SQL execution goes through DirectToolExecutor\n")
    print('👋 First time here? Try: "show trips in January 2022 by week"\n')

    while True:
        try:
            q = input("Ask a question: ").strip()
            sql = None
            df = None
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!\n")
            break

        if not q:
            continue

        if q.lower() in ("exit", "quit", "bye", "q"):
            print("\n👋 Goodbye!\n")
            break

        if q.lower() == "reset":
            state = reset_session()
            print("Session reset.\n")
            continue

        # Security: SQL injection
        if detect_sql_injection(q):
            print("\n🚫 That looks like a SQL injection attempt.")
            print("I only run safe, pre-built SELECT queries.\n")
            continue

        # Simple help
        if q.lower() == "help":
            contextual_help(q)
            continue

        # Explain last result
        if any(k in q.lower() for k in ["explain the result", "explain this", "explain it", "eli5", "like i'm new", "like i am new"]):
            style = "newbie" if ("new" in q.lower() or "eli5" in q.lower()) else "simple"
            explain_last_result(state, style=style)
            continue

        # Unsupported queries
        unsupported = detect_unsupported_query(q)
        if unsupported:
            print("\n" + unsupported)
            print("\nTry: 'show trips in summer 2022 by week'\n")
            continue

        # Multi-topic detection
        multi = detect_multi_topic(q)
        if multi:
            print(f"\n❓ I noticed you mentioned multiple topics: {', '.join(multi)}")
            print("I can only analyze one at a time. Which would you like?\n")
            for i, topic in enumerate(multi, 1):
                print(f"  {i}) {topic}")
            while True:
                try:
                    raw = input(f"Choose 1-{len(multi)}: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n")
                    raw = "1"
                if raw.isdigit() and 1 <= int(raw) <= len(multi):
                    chosen = multi[int(raw) - 1]
                    q = re.sub(r"\b(trip|trips|ride|rides|fare|fares|tip|tips|vendor|vendors)\b", "", q, flags=re.I).strip()
                    q = (q + " " + chosen).strip()
                    break
                print(f"  ⚠️  Choose 1-{len(multi)}.")

        # Preserve follow-up context
        last_suggestions = state.get("_last_suggestions", [])
        last_context = state.get("_last_query_context")
        query_count = state.get("_query_count", 0)

        state = reset_session()
        state["_last_suggestions"] = last_suggestions
        state["_last_query_context"] = last_context
        state["_query_count"] = query_count

        needs_busier = _needs_busier_clarification(q)

        # Semantic rewrite (LLM optional)
        rewrite = semantic_rewrite(model, q)
        rewritten = (rewrite.get("rewritten") or q).strip()

        # Apply LLM hints
        if rewrite.get("granularity_hint") in ("daily", "weekly", "monthly"):
            state["granularity"] = rewrite["granularity_hint"]
        if rewrite.get("metric_hint") in ("avg", "total"):
            state["metric"] = rewrite["metric_hint"]

        extract_slots_from_text(state, rewritten)

        if state.get("_dates_were_swapped"):
            f = state.get("_swapped_from")
            tto = state.get("_swapped_to")
            state["_dates_were_swapped"] = False
            if f and tto:
                print(f"\n🔁 I noticed the dates were reversed ({f} → {tto}). I'll use {tto} to {f} instead.\n")

        if state.get("_saw_invalid_iso_date"):
            inv = ", ".join(state.get("_invalid_dates") or [])
            print(f"\n⚠️  Found invalid date(s): {inv}")
            print("    Tip: Use YYYY-MM-DD (example: 2022-06-15)\n")
            print("  Let's enter valid dates.\n")
            state["start_date"] = None
            state["end_date"] = None
            state["_saw_invalid_iso_date"] = False
            state["_invalid_dates"] = []

        # Route
        route = ask_router(model, rewritten)
        if not route.get("dataset_match", True):
            print("\n❌ Out of scope (NYC Yellow Taxi 2022 only).")
            print("Try: trips, fares, tips, or vendors in 2022.\n")
            continue

        intent = route.get("intent", "unknown")

        # busier clarification override
        if needs_busier:
            intent, ok = _clarify_busier(state)
            if not ok:
                continue

        if intent not in SUPPORTED_INTENTS:
            print("\n❓ I can help with: trips, fares, tips, or vendors.")
            print('Try: "show trips in January 2022 by week"\n')
            continue

        state["intent"] = intent

        # If sample and no dates, reuse last range
        if intent == "sample_rows" and (state.get("start_date") is None or state.get("end_date") is None):
            ctx = state.get("_last_query_context") or {}
            if ctx.get("start_date") and ctx.get("end_date"):
                state["start_date"] = ctx["start_date"]
                state["end_date"] = ctx["end_date"]

        # Fill missing slots
        for slot in missing_slots(state, intent):
            if slot == "start_date":
                state["start_date"] = _prompt_date("start_date", "2022-06-01")
            elif slot == "end_date":
                state["end_date"] = _prompt_date("end_date", "2022-09-01")
            elif slot == "granularity":
                if state["start_date"] and state["end_date"]:
                    suggestion = recommend_granularity(state["start_date"], state["end_date"])
                    days = (state["end_date"] - state["start_date"]).days
                    print(f"\n💡 For a {days}-day range, '{suggestion}' often works well.")
                else:
                    suggestion = "weekly"
                state["granularity"] = _prompt_choice(
                    "granularity (daily/weekly/monthly)",
                    ["daily", "weekly", "monthly"],
                    default=suggestion,
                )
            elif slot == "metric":
                print("\nMetric controls how we aggregate money:")
                print("  - avg   = average per trip")
                print("  - total = total sum in the period")
                state["metric"] = _prompt_choice("metric (avg/total)", ["avg", "total"], default="avg")

        # Optional limit for sampling
        if intent == "sample_rows" and not state.get("limit"):
            while True:
                try:
                    raw_lim = input("limit (rows to show) [100]: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n")
                    raise
                if not raw_lim:
                    state["limit"] = 100
                    break
                if raw_lim.isdigit():
                    lim = int(raw_lim)
                    if 1 <= lim <= 1000:
                        state["limit"] = lim
                        break
                print("  ⚠️  Enter a number between 1 and 1000.")

        # Validate dates
        try:
            validate_dates_state(state)
        except Exception as e:
            print(f"\n  ⚠️  {e}")
            print("Let's fix the dates.\n")
            state["start_date"] = _prompt_date("start_date", "2022-06-01")
            state["end_date"] = _prompt_date("end_date", "2022-09-01")
            try:
                validate_dates_state(state)
            except Exception as e2:
                print(f"\n  ⚠️  {e2}\nCancelled.\n")
                continue

        if not validate_all_slots(state):
            print("Cannot proceed. Try again.\n")
            continue

        # Granularity warnings
        if intent in ("trip_frequency", "fare_trend", "tip_trend") and state.get("granularity"):
            days = (state["end_date"] - state["start_date"]).days
            if days <= 7 and state["granularity"] != "daily":
                print(f"\n💡 Note: Your range is only {days} day(s).")
                print("   Daily usually makes more sense than weekly/monthly for such a short window.")
                if not _prompt_yes_no("Continue with this granularity?"):
                    state["granularity"] = "daily"

        if intent in ("trip_frequency", "fare_trend", "tip_trend") and state.get("granularity") == "daily":
            days = (state["end_date"] - state["start_date"]).days
            if days > 90:
                print(f"\n⚠️  Daily granularity for {days} days = many rows.")
                print("   Consider 'weekly' or 'monthly' for clearer trends.")
                if not _prompt_yes_no("Continue with daily?"):
                    state["granularity"] = _prompt_choice("Choose granularity", ["weekly", "monthly"], default="weekly")

        # Plan
        sd = state["start_date"].strftime("%Y-%m-%d")
        ed = state["end_date"].strftime("%Y-%m-%d")
        gran = state.get("granularity")
        metric = state.get("metric")

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
        rows = estimate_rows(state, intent)
        print(f"💾 Expected output: {rows} rows")
        # ============================================================
        # MCP INTEGRATION: Show that execution goes through MCP
        # ============================================================
        print(f"🔗 Execution: via MCP DirectToolExecutor")
        print("="*60 + "\n")

        if not _prompt_yes_no("Does this look correct?"):
            print("Cancelled.\n")
            continue

        print("\n📊 What this query does:")
        print(f"   {explain_sql(state, intent)}\n")

        sql = safe_select_only(build_sql(state, intent))
        print("SQL:")
        print(sql)
        print()

        if not _prompt_yes_no("Run query?"):
            print("Cancelled.\n")
            continue

        # ============================================================
        # MCP INTEGRATION: Execute through MCP boundary
        # THIS IS THE KEY CHANGE - no longer calling execute_sql_query() directly
        # ============================================================
        print("⏳ Running query via MCP tool executor...")
        try:
            df = _execute_via_mcp(sql)
            print("✅ Query complete (executed via MCP)!\n")
        except Exception as e:
            print(f"\n❌ Query failed: {e}")
            print("This might be a bug — please report it.\n")
            continue

        if len(df) == 0:
            print("⚠️  Query returned 0 rows.")
            print("Try expanding the date range.\n")
            continue

        print(df.head(20))
        print(f"\nDone. Returned {len(df)} rows.\n")

        # save context
        if sql is not None:
            state["_last_sql"] = sql
        state["_last_df"] = df
        state["_last_df_rows"] = len(df)
        state["_last_user_question"] = q
        try:
            state["_query_count"] = int(state.get("_query_count", 0)) + 1
        except Exception:
            state["_query_count"] = 1
        state["_last_query_context"] = {
            "intent": state.get("intent"),
            "start_date": state.get("start_date"),
            "end_date": state.get("end_date"),
            "granularity": state.get("granularity"),
            "metric": state.get("metric"),
            "query_num": state.get("_query_count", 0),
        }
        suggest_followup(state, intent)

if __name__ == "__main__":
    run_agent()
