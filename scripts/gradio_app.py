"""
Gradio Frontend for Symbiote Lite Analyst Agent
A human-in-the-loop AI analyst with approval gates

Place this file in: symbiote-lite-analyst-agent/scripts/gradio_app.py
Run with: python -m scripts.gradio_app
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr
from gradio import ChatMessage

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import your existing modules
from symbiote_lite.router import configure_model, ask_router, semantic_rewrite
from symbiote_lite.slots import (
    reset_session,
    missing_slots,
    extract_slots_from_text,
    validate_all_slots,
    SUPPORTED_INTENTS,
)
from symbiote_lite.dates import recommend_granularity
from symbiote_lite.sql.builder import build_sql
from symbiote_lite.sql.safety import safe_select_only, detect_sql_injection
from symbiote_lite.tools.executor import DirectToolExecutor
from symbiote_lite.explain import explain_sql, estimate_rows, DATASET_YEAR

# ============================================================
# AGENT STATE MANAGEMENT
# ============================================================

class GradioAgentState:
    """
    Manages conversation state for the Gradio interface.
    Replaces the CLI's input() prompts with a state machine.
    """
    
    # Workflow stages
    STAGE_IDLE = "idle"
    STAGE_AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    STAGE_AWAITING_SQL_APPROVAL = "awaiting_sql_approval"
    STAGE_AWAITING_SLOT = "awaiting_slot"
    STAGE_AWAITING_CLARIFICATION = "awaiting_clarification"
    
    def __init__(self):
        self.model = configure_model()
        self.executor = DirectToolExecutor()
        self.reset()
    
    def reset(self):
        """Reset all state for a new conversation"""
        self.state = reset_session()
        self.stage = self.STAGE_IDLE
        self.pending_sql = None
        self.pending_slot = None
        self.pending_clarification = None
        self.last_query = None
    
    def get_model_status(self) -> str:
        """Return model status string"""
        if os.getenv("OPENAI_API_KEY") and self.model:
            return "✅ LLM routing enabled"
        return "ℹ️ Deterministic mode (no LLM)"


# Global agent instance
agent = GradioAgentState()


# ============================================================
# UNSUPPORTED QUERY DETECTION (from your agent.py)
# ============================================================

import re

UNSUPPORTED_PATTERNS = [
    (r"\b(weekend|weekday|saturday|sunday|weekends|weekdays)\s.*(busy|busier|more|less|compar|vs|than)",
     "Weekend vs weekday breakdown isn't supported yet. Try daily/weekly/monthly aggregation."),
    (r"\b(hour|hourly|morning|evening|afternoon|night|midnight|noon)\b",
     "Hourly breakdown isn't supported yet. Try: daily, weekly, or monthly."),
    (r"\b(location|borough|zone|pickup.?location|dropoff.?location|manhattan|brooklyn|queens|bronx|staten)\b",
     "Location-based analysis isn't supported yet. I can analyze trips, fares, tips, and vendors over time."),
    (r"\b(driver|drivers|driver.?id)\b",
     "Driver-level analysis isn't available. I can show vendor (company) level data instead."),
    (r"\b(passenger|passengers|rider|riders)\b",
     "Passenger-level analysis isn't available. I can analyze trip counts, fares, and tips over time."),
    (r"\b(distance|mile|miles|km|kilometer)\b",
     "Distance-based analysis isn't supported yet. Try: fare trends or trip counts instead."),
    (r"\b(payment|cash|card|credit|debit)\b",
     "Payment type breakdown isn't supported yet. I can analyze total fares, tips, and trip counts."),
]

def detect_unsupported_query(user_input: str) -> Optional[str]:
    t = (user_input or "").lower()
    for pattern, explanation in UNSUPPORTED_PATTERNS:
        if re.search(pattern, t):
            return explanation
    return None


def needs_busier_clarification(user_input: str) -> bool:
    t = user_input.lower()
    busy = ["busier", "busy", "more active", "less active", "quieter", "slower"]
    comparison = ["vs", "versus", "compared", "than", "or"]
    return any(b in t for b in busy) and any(c in t for c in comparison)


# ============================================================
# FORMATTING HELPERS
# ============================================================

def format_plan(state: Dict[str, Any], intent: str) -> str:
    """Format the execution plan for display"""
    sd = state["start_date"].strftime("%Y-%m-%d")
    ed = state["end_date"].strftime("%Y-%m-%d")
    gran = state.get("granularity")
    metric = state.get("metric")
    
    task_names = {
        "trip_frequency": "Count trips over time",
        "vendor_inactivity": "Rank vendors by trip count (lowest = most inactive)",
        "fare_trend": f"{'Sum' if metric=='total' else 'Average'} fares over time",
        "tip_trend": f"{'Sum' if metric=='total' else 'Average'} tips over time",
        "sample_rows": "Show a sample of raw trip rows",
    }
    
    rows = estimate_rows(state, intent)
    
    plan_lines = [
        "## 🧠 EXECUTION PLAN",
        "",
        f"**📌 Task:** {task_names.get(intent, 'Analyze data')}",
        f"**📅 Period:** {sd} to {ed} *(end date exclusive)*",
    ]
    
    if gran:
        plan_lines.append(f"**⏱️ Granularity:** {gran}")
    if metric and intent in ("fare_trend", "tip_trend"):
        plan_lines.append(f"**📊 Metric:** {metric}")
    
    plan_lines.extend([
        f"**💾 Expected rows:** ~{rows}",
        f"**🔗 Execution:** MCP DirectToolExecutor",
        "",
        "---",
        "",
        "Does this look correct? Reply **yes** to continue or **no** to cancel."
    ])
    
    return "\n".join(plan_lines)


def format_sql_approval(sql: str, state: Dict[str, Any], intent: str) -> str:
    """Format SQL for approval display"""
    explanation = explain_sql(state, intent)
    
    return f"""## 📊 Query Explanation

{explanation}

## 📝 Generated SQL

```sql
{sql}
```

---

Run this query? Reply **yes** to execute or **no** to cancel."""


def format_results(df, state: Dict[str, Any], intent: str) -> str:
    """Format query results for display"""
    if df is None or len(df) == 0:
        return "⚠️ Query returned 0 rows. Try expanding the date range."
    
    # Convert DataFrame to markdown table
    table = df.head(20).to_markdown(index=False)
    
    result_lines = [
        "## ✅ Query Results",
        "",
        table,
        "",
    ]
    
    if len(df) > 20:
        result_lines.append(f"*Showing first 20 of {len(df)} rows*")
    else:
        result_lines.append(f"*{len(df)} rows returned*")
    
    # Add simple analysis
    result_lines.extend(["", "---", "", "**💡 What's next?** Ask another question or refine this analysis."])
    
    return "\n".join(result_lines)


def format_slot_prompt(slot: str, state: Dict[str, Any]) -> str:
    """Format prompt for missing slot"""
    if slot == "start_date":
        return "📅 **Start date needed**\n\nPlease provide a start date in YYYY-MM-DD format (2022 only).\n\nExample: `2022-01-01`"
    
    elif slot == "end_date":
        return "📅 **End date needed**\n\nPlease provide an end date in YYYY-MM-DD format (2022 only).\n\nNote: End date is *exclusive* (2022-02-01 means up to Jan 31).\n\nExample: `2022-02-01`"
    
    elif slot == "granularity":
        suggestion = "weekly"
        if state.get("start_date") and state.get("end_date"):
            suggestion = recommend_granularity(state["start_date"], state["end_date"])
            days = (state["end_date"] - state["start_date"]).days
            return f"""⏱️ **Granularity needed**

Your date range is {days} days. I recommend **{suggestion}**.

Choose one:
- `daily` - one row per day
- `weekly` - one row per week  
- `monthly` - one row per month

Or just type `{suggestion}` to use my recommendation."""
        
        return "⏱️ **Granularity needed**\n\nChoose: `daily`, `weekly`, or `monthly`"
    
    elif slot == "metric":
        return """📊 **Metric needed**

How should I aggregate the amounts?

- `avg` - average per trip (typical fare/tip)
- `total` - sum of all fares/tips in period

Choose one: `avg` or `total`"""
    
    return f"Please provide: {slot}"


# ============================================================
# MAIN CHAT HANDLER
# ============================================================

def process_message(user_message: str, history: List) -> str:
    """
    Main message processor - handles the approval workflow.
    """
    global agent
    
    user_message = user_message.strip()
    if not user_message:
        return "Please enter a question or response."
    
    user_lower = user_message.lower()
    
    # ========================================
    # HANDLE SPECIAL COMMANDS
    # ========================================
    
    if user_lower in ("reset", "clear", "start over"):
        agent.reset()
        return "🔄 Session reset. What would you like to analyze?"
    
    if user_lower in ("help", "?"):
        return get_help_text()
    
    # ========================================
    # HANDLE APPROVAL RESPONSES
    # ========================================
    
    if agent.stage == agent.STAGE_AWAITING_PLAN_APPROVAL:
        if user_lower in ("yes", "y", "approve", "ok", "okay", "sure", "proceed"):
            return handle_plan_approved()
        elif user_lower in ("no", "n", "cancel", "stop", "abort", "nope"):
            agent.stage = agent.STAGE_IDLE
            return "❌ Plan cancelled. What else would you like to analyze?"
        else:
            return "Please reply **yes** to approve the plan or **no** to cancel."
    
    if agent.stage == agent.STAGE_AWAITING_SQL_APPROVAL:
        if user_lower in ("yes", "y", "run", "execute", "ok", "okay", "sure"):
            return handle_sql_approved()
        elif user_lower in ("no", "n", "cancel", "stop", "abort", "nope"):
            agent.stage = agent.STAGE_IDLE
            return "❌ Query cancelled. What else would you like to analyze?"
        else:
            return "Please reply **yes** to run the query or **no** to cancel."
    
    if agent.stage == agent.STAGE_AWAITING_SLOT:
        return handle_slot_response(user_message)
    
    if agent.stage == agent.STAGE_AWAITING_CLARIFICATION:
        return handle_clarification_response(user_message)
    
    # ========================================
    # PROCESS NEW QUERY
    # ========================================
    
    return process_new_query(user_message)


def process_new_query(query: str) -> str:
    """Process a new analytical query"""
    global agent
    
    # Security check
    if detect_sql_injection(query):
        return "🚫 That looks like a SQL injection attempt. I only run safe, pre-built SELECT queries."
    
    # Check for unsupported queries
    unsupported = detect_unsupported_query(query)
    if unsupported:
        return f"⚠️ {unsupported}\n\nTry: *show trips in January 2022 by week*"
    
    # Check for "busier" clarification
    if needs_busier_clarification(query):
        agent.stage = agent.STAGE_AWAITING_CLARIFICATION
        agent.pending_clarification = "busier"
        agent.last_query = query
        return """❓ **Quick clarification**

When you say *busier*, do you mean:

1. **Number of trips** (more rides = busier)
2. **Total revenue** (more money = busier)
3. **Average fare** per trip

Reply with `1`, `2`, or `3`."""
    
    # Reset state but preserve context
    last_context = agent.state.get("_last_query_context")
    agent.state = reset_session()
    agent.state["_last_query_context"] = last_context
    agent.last_query = query
    
    # Semantic rewrite (LLM optional)
    rewrite = semantic_rewrite(agent.model, query)
    rewritten = (rewrite.get("rewritten") or query).strip()
    
    # Apply LLM hints
    if rewrite.get("granularity_hint") in ("daily", "weekly", "monthly"):
        agent.state["granularity"] = rewrite["granularity_hint"]
    if rewrite.get("metric_hint") in ("avg", "total"):
        agent.state["metric"] = rewrite["metric_hint"]
    
    # Extract slots from text
    extract_slots_from_text(agent.state, rewritten)
    
    # Route the intent
    route = ask_router(agent.model, rewritten)
    
    if not route.get("dataset_match", True):
        return "❌ **Out of scope**\n\nI only analyze NYC Yellow Taxi data from 2022.\n\nTry: trips, fares, tips, or vendors in 2022."
    
    intent = route.get("intent", "unknown")
    
    if intent not in SUPPORTED_INTENTS:
        return "❓ I can help with: **trips**, **fares**, **tips**, or **vendors**.\n\nTry: *show trips in January 2022 by week*"
    
    agent.state["intent"] = intent
    
    # Check for missing slots
    missing = missing_slots(agent.state, intent)
    
    if missing:
        # Need to collect slots
        agent.pending_slot = missing[0]
        agent.stage = agent.STAGE_AWAITING_SLOT
        return format_slot_prompt(missing[0], agent.state)
    
    # All slots filled - validate and show plan
    return show_plan()


def handle_slot_response(response: str) -> str:
    """Handle user response to slot prompt"""
    global agent
    
    slot = agent.pending_slot
    response = response.strip()
    
    try:
        if slot == "start_date":
            from symbiote_lite.dates import validate_date, _parse_date
            validate_date(response)
            agent.state["start_date"] = _parse_date(response)
        
        elif slot == "end_date":
            from symbiote_lite.dates import validate_date, _parse_date
            validate_date(response)
            agent.state["end_date"] = _parse_date(response)
        
        elif slot == "granularity":
            from symbiote_lite.slots import normalize_granularity
            agent.state["granularity"] = normalize_granularity(response)
        
        elif slot == "metric":
            from symbiote_lite.slots import normalize_metric
            agent.state["metric"] = normalize_metric(response)
        
    except ValueError as e:
        return f"⚠️ {e}\n\n{format_slot_prompt(slot, agent.state)}"
    
    # Check for more missing slots
    intent = agent.state["intent"]
    missing = missing_slots(agent.state, intent)
    
    if missing:
        agent.pending_slot = missing[0]
        return format_slot_prompt(missing[0], agent.state)
    
    # All slots filled - show plan
    agent.pending_slot = None
    agent.stage = agent.STAGE_IDLE
    return show_plan()


def handle_clarification_response(response: str) -> str:
    """Handle clarification responses (like 'busier' meaning)"""
    global agent
    
    response = response.strip()
    
    if agent.pending_clarification == "busier":
        if response == "1":
            agent.state["intent"] = "trip_frequency"
        elif response == "2":
            agent.state["intent"] = "fare_trend"
            agent.state["metric"] = "total"
        elif response == "3":
            agent.state["intent"] = "fare_trend"
            agent.state["metric"] = "avg"
        else:
            return "Please reply with `1`, `2`, or `3`."
        
        agent.pending_clarification = None
        agent.stage = agent.STAGE_IDLE
        
        # Re-process with the clarified intent
        query = agent.last_query
        rewrite = semantic_rewrite(agent.model, query)
        rewritten = (rewrite.get("rewritten") or query).strip()
        extract_slots_from_text(agent.state, rewritten)
        
        # Check for missing slots
        intent = agent.state["intent"]
        missing = missing_slots(agent.state, intent)
        
        if missing:
            agent.pending_slot = missing[0]
            agent.stage = agent.STAGE_AWAITING_SLOT
            return format_slot_prompt(missing[0], agent.state)
        
        return show_plan()
    
    return "Something went wrong. Please type `reset` and try again."


def show_plan() -> str:
    """Validate slots and show execution plan"""
    global agent
    
    # Validate dates
    try:
        from symbiote_lite.slots import validate_dates_state
        validate_dates_state(agent.state)
    except Exception as e:
        agent.state["start_date"] = None
        agent.state["end_date"] = None
        agent.pending_slot = "start_date"
        agent.stage = agent.STAGE_AWAITING_SLOT
        return f"⚠️ Date error: {e}\n\n{format_slot_prompt('start_date', agent.state)}"
    
    if not validate_all_slots(agent.state):
        agent.stage = agent.STAGE_IDLE
        return "⚠️ Something went wrong with validation. Please try again."
    
    intent = agent.state["intent"]
    agent.stage = agent.STAGE_AWAITING_PLAN_APPROVAL
    
    return format_plan(agent.state, intent)


def handle_plan_approved() -> str:
    """Handle plan approval - build and show SQL"""
    global agent
    
    intent = agent.state["intent"]
    sql = safe_select_only(build_sql(agent.state, intent))
    agent.pending_sql = sql
    agent.stage = agent.STAGE_AWAITING_SQL_APPROVAL
    
    return format_sql_approval(sql, agent.state, intent)


def handle_sql_approved() -> str:
    """Handle SQL approval - execute query"""
    global agent
    
    sql = agent.pending_sql
    
    try:
        result = agent.executor.execute_sql(sql)
        df = result.get("dataframe")
        
        if df is None or len(df) == 0:
            agent.stage = agent.STAGE_IDLE
            agent.pending_sql = None
            return "⚠️ Query returned 0 rows. Try expanding the date range or adjusting parameters."
        
        # Store results in state
        agent.state["_last_sql"] = sql
        agent.state["_last_df"] = df
        agent.state["_last_query_context"] = {
            "intent": agent.state.get("intent"),
            "start_date": agent.state.get("start_date"),
            "end_date": agent.state.get("end_date"),
            "granularity": agent.state.get("granularity"),
            "metric": agent.state.get("metric"),
        }
        
        agent.stage = agent.STAGE_IDLE
        agent.pending_sql = None
        
        return format_results(df, agent.state, agent.state["intent"])
        
    except Exception as e:
        agent.stage = agent.STAGE_IDLE
        agent.pending_sql = None
        return f"❌ Query failed: {e}\n\nThis might be a bug — please try again or simplify your question."


def get_help_text() -> str:
    """Return help text"""
    return f"""## 🧠 Symbiote Lite — NYC Taxi Analyst ({DATASET_YEAR})

**What I can do:**
- Turn your question into safe SELECT-only SQL over `taxi_trips`
- Show a plan + SQL, then run only after you approve
- Analyze trips, fares, tips, and vendor activity

**Data constraints:**
- Dates must be in {DATASET_YEAR}
- End date is EXCLUSIVE (end_date=2022-02-01 includes up to Jan 31)

**Example questions:**
- *show trips from January 2022 by week*
- *average fares in summer 2022 by month*
- *total tips in Q2 2022*
- *which vendors were inactive in November?*

**Commands:**
- `reset` — clear state and start over
- `help` — show this message"""


# ============================================================
# GRADIO UI (Compatible with Gradio 6.0)
# ============================================================

def create_interface():
    """Create and configure the Gradio interface"""
    
    with gr.Blocks(title="Symbiote Lite Analyst") as demo:
        
        gr.Markdown(f"""
        # 🔬 Symbiote Lite Analyst Agent
        
        A human-in-the-loop AI analyst for NYC taxi trip data ({DATASET_YEAR}).
        
        **How it works:** Ask a question → Review the plan → Approve the SQL → Get results
        
        {agent.get_model_status()} | 🔗 MCP DirectToolExecutor
        """)
        
        # Chatbot with messages format (Gradio 6.0)
        chatbot = gr.Chatbot(
            label="Chat",
            height=400,
        )
        
        msg = gr.Textbox(
            label="Your message",
            placeholder="Try: show trips in January 2022 by week",
            lines=1,
        )
        
        with gr.Row():
            submit_btn = gr.Button("Send", variant="primary")
            clear_btn = gr.Button("🗑️ Clear Chat")
        
        gr.Markdown("### 💡 Example queries (click to use)")
        
        with gr.Row():
            ex1 = gr.Button("Trips in Jan 2022 by week", size="sm")
            ex2 = gr.Button("Avg fares in Feb by day", size="sm")
            ex3 = gr.Button("Total tips in Q2 by month", size="sm")
            ex4 = gr.Button("Inactive vendors in Nov", size="sm")
        
        gr.Markdown("""
        ---
        ⚠️ *This agent only executes SELECT queries and always asks for approval first.*
        
        Type `help` for more info or `reset` to start over.
        """)
        
        # ========================================
        # Event handlers (Gradio 6.0 message format)
        # ========================================
        
        def respond(message: str, chat_history: List):
            if not message.strip():
                return "", chat_history
            
            # Add user message (dict format for Gradio 6.0)
            chat_history = chat_history + [{"role": "user", "content": message}]
            
            # Get response
            response = process_message(message, chat_history)
            
            # Add assistant response (dict format for Gradio 6.0)
            chat_history = chat_history + [{"role": "assistant", "content": response}]
            
            return "", chat_history
        
        def clear_chat():
            agent.reset()
            return [], ""
        
        def use_example(example_text: str, chat_history: List):
            return respond(example_text, chat_history)
        
        # Submit on enter or button click
        msg.submit(respond, [msg, chatbot], [msg, chatbot])
        submit_btn.click(respond, [msg, chatbot], [msg, chatbot])
        
        # Clear button
        clear_btn.click(clear_chat, outputs=[chatbot, msg])
        
        # Example buttons
        ex1.click(lambda h: use_example("show trips in January 2022 by week", h), [chatbot], [msg, chatbot])
        ex2.click(lambda h: use_example("average fares in February 2022 by day", h), [chatbot], [msg, chatbot])
        ex3.click(lambda h: use_example("total tips in Q2 2022 by month", h), [chatbot], [msg, chatbot])
        ex4.click(lambda h: use_example("which vendors were inactive in November 2022", h), [chatbot], [msg, chatbot])
    
    return demo


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # Check for tabulate (needed for DataFrame.to_markdown())
    try:
        import tabulate
    except ImportError:
        print("Installing tabulate for table formatting...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tabulate", "-q"])
    
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
