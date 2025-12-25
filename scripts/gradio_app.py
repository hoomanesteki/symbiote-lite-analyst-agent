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
# WELCOME MESSAGE
# ============================================================

WELCOME_MESSAGE = f"""## 👋 Welcome to Symbiote Lite Analyst!

I'm your **AI-powered data analyst** for NYC Yellow Taxi trips ({DATASET_YEAR}).

---

### 🎯 What I Can Help You With

| Analysis Type | Example Question |
|---------------|------------------|
| 🚕 **Trip Counts** | "How many trips in January 2022?" |
| 💰 **Fare Analysis** | "Average fares in Q1 2022 by week" |
| 💵 **Tip Trends** | "Total tips in summer 2022 by month" |
| 🏢 **Vendor Activity** | "Which vendors were inactive in March?" |

---

### 🔄 How It Works (Human-in-the-Loop)

1️⃣ **Ask** → Type your question in plain English  
2️⃣ **Review** → I'll show you the execution plan  
3️⃣ **Approve** → Click ✅ Yes to approve the SQL query  
4️⃣ **Results** → See your data in a nice table!

---

### 💡 Quick Start

Click one of the **example buttons** below, or type your own question!

> **Pro tip:** Use the ✅ Yes and ❌ No buttons for quick approvals!
"""


# ============================================================
# CSS STYLING
# ============================================================

CUSTOM_CSS = """
/* Full width container */
.gradio-container {
    max-width: 100% !important;
    padding: 0 20px !important;
}

/* Main chat area - wider and taller */
#chatbot {
    height: 55vh !important;
    min-height: 400px !important;
    border-radius: 12px !important;
    border: 1px solid #e0e0e0 !important;
}

/* Dark mode adjustments */
.dark #chatbot {
    border-color: #374151 !important;
    background: #1f2937 !important;
}

/* Message styling */
#chatbot .message {
    font-size: 14px !important;
    line-height: 1.6 !important;
}

/* Tables in chat */
#chatbot table {
    font-size: 13px !important;
    width: 100% !important;
    margin: 10px 0 !important;
}

#chatbot th {
    background: #f3f4f6 !important;
    font-weight: 600 !important;
}

.dark #chatbot th {
    background: #374151 !important;
}

/* Quick action buttons */
.quick-btn {
    min-width: 80px !important;
    font-weight: 600 !important;
}

.quick-btn-yes {
    background: #10b981 !important;
    color: white !important;
}

.quick-btn-no {
    background: #ef4444 !important;
    color: white !important;
}

/* Example buttons row */
.example-row {
    gap: 8px !important;
}

.example-btn {
    font-size: 13px !important;
    padding: 8px 12px !important;
}

/* Status badges */
.status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    margin-right: 8px;
}

.badge-green {
    background: #d1fae5;
    color: #065f46;
}

.badge-blue {
    background: #dbeafe;
    color: #1e40af;
}

.dark .badge-green {
    background: #064e3b;
    color: #6ee7b7;
}

.dark .badge-blue {
    background: #1e3a5f;
    color: #93c5fd;
}

/* Input area */
#msg-input {
    border-radius: 10px !important;
}

/* Workflow indicator */
.workflow-step {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: #f1f5f9;
    border-radius: 6px;
    font-size: 12px;
    margin: 2px;
}

.dark .workflow-step {
    background: #334155;
}

.step-number {
    width: 20px;
    height: 20px;
    background: #3b82f6;
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
}
"""


# ============================================================
# AGENT STATE MANAGEMENT
# ============================================================

class GradioAgentState:
    """Manages conversation state for the Gradio interface."""
    
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
            return "LLM Active"
        return "Deterministic"


# Global agent instance
agent = GradioAgentState()


# ============================================================
# UNSUPPORTED QUERY DETECTION
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
        "trip_frequency": "📊 Count trips over time",
        "vendor_inactivity": "🏢 Rank vendors by activity",
        "fare_trend": f"💰 {'Sum' if metric=='total' else 'Average'} fares over time",
        "tip_trend": f"💵 {'Sum' if metric=='total' else 'Average'} tips over time",
        "sample_rows": "📋 Show sample trip rows",
    }
    
    rows = estimate_rows(state, intent)
    
    return f"""## 🎯 Execution Plan

| Parameter | Value |
|-----------|-------|
| **Task** | {task_names.get(intent, 'Analyze data')} |
| **Date Range** | {sd} → {ed} *(end exclusive)* |
| **Granularity** | {gran} |
| **Expected Rows** | ~{rows} |
| **Executor** | MCP DirectToolExecutor |

---

### ✅ Action Required

**Does this look correct?**

👉 Click **✅ Yes** to continue or **❌ No** to cancel

*Or type `yes` / `no`*"""


def format_sql_approval(sql: str, state: Dict[str, Any], intent: str) -> str:
    """Format SQL for approval display"""
    explanation = explain_sql(state, intent)
    
    return f"""## 🔍 Query Preview

{explanation}

### 📝 SQL Query

```sql
{sql}
```

---

### ⚠️ Safety Check

This is a **read-only SELECT query** — it won't modify any data.

👉 Click **✅ Yes** to execute or **❌ No** to cancel

*Or type `yes` / `no`*"""


def format_results(df, state: Dict[str, Any], intent: str) -> str:
    """Format query results for display"""
    if df is None or len(df) == 0:
        return """## ⚠️ No Results Found

The query returned 0 rows. This could mean:
- The date range has no data
- The filters are too restrictive

**💡 Try:** Expanding the date range or adjusting your question."""
    
    table = df.head(20).to_markdown(index=False)
    
    result_lines = [
        "## ✅ Query Results",
        "",
        table,
        "",
    ]
    
    if len(df) > 20:
        result_lines.append(f"*📊 Showing first 20 of {len(df)} rows*")
    else:
        result_lines.append(f"*📊 {len(df)} rows returned*")
    
    result_lines.extend([
        "",
        "---",
        "",
        "### 🎉 Success!",
        "",
        "**What's next?**",
        "- Ask another question",
        "- Click an example button below",
        "- Type `reset` to start fresh",
    ])
    
    return "\n".join(result_lines)


def format_slot_prompt(slot: str, state: Dict[str, Any]) -> str:
    """Format prompt for missing slot with helpful guidance"""
    if slot == "start_date":
        return """## 📅 Start Date Needed

Please enter the **start date** for your analysis.

| Format | Example |
|--------|---------|
| YYYY-MM-DD | `2022-01-01` |

> **💡 Tip:** Data is available for all of 2022 (Jan 1 - Dec 31)

**Quick options:**
- `2022-01-01` — Start of year
- `2022-04-01` — Start of Q2
- `2022-07-01` — Start of Q3"""

    elif slot == "end_date":
        return """## 📅 End Date Needed

Please enter the **end date** for your analysis.

| Format | Example |
|--------|---------|
| YYYY-MM-DD | `2022-02-01` |

> **⚠️ Note:** End date is *exclusive* — `2022-02-01` means data up to Jan 31st

**Quick options:**
- `2022-02-01` — End of January
- `2022-04-01` — End of Q1
- `2022-07-01` — End of Q2"""

    elif slot == "granularity":
        suggestion = "weekly"
        if state.get("start_date") and state.get("end_date"):
            suggestion = recommend_granularity(state["start_date"], state["end_date"])
            days = (state["end_date"] - state["start_date"]).days
            return f"""## ⏱️ Granularity Needed

Your date range spans **{days} days**.

| Option | Description | Recommendation |
|--------|-------------|----------------|
| `daily` | One row per day | Best for < 2 weeks |
| `weekly` | One row per week | Best for 2 weeks - 3 months |
| `monthly` | One row per month | Best for > 3 months |

**🎯 Recommended:** `{suggestion}`

*Type your choice or just enter `{suggestion}`*"""
        
        return """## ⏱️ Granularity Needed

Choose how to group your data:

| Option | Description |
|--------|-------------|
| `daily` | One row per day |
| `weekly` | One row per week |
| `monthly` | One row per month |"""

    elif slot == "metric":
        return """## 📊 Metric Needed

How should I calculate the values?

| Option | Description | Use Case |
|--------|-------------|----------|
| `avg` | Average per trip | "What's the typical fare?" |
| `total` | Sum of all trips | "How much revenue total?" |

*Type `avg` or `total`*"""

    return f"Please provide: **{slot}**"


# ============================================================
# MAIN CHAT HANDLER
# ============================================================

def process_message(user_message: str, history: List) -> str:
    """Main message processor - handles the approval workflow."""
    global agent
    
    user_message = user_message.strip()
    if not user_message:
        return "Please enter a question or response."
    
    user_lower = user_message.lower()
    
    # Handle special commands
    if user_lower in ("reset", "clear", "start over"):
        agent.reset()
        return "## 🔄 Session Reset\n\nI've cleared everything. What would you like to analyze?\n\n*Click an example below or type your question!*"
    
    if user_lower in ("help", "?"):
        return WELCOME_MESSAGE
    
    # Handle approval responses
    if agent.stage == agent.STAGE_AWAITING_PLAN_APPROVAL:
        if user_lower in ("yes", "y", "approve", "ok", "okay", "sure", "proceed"):
            return handle_plan_approved()
        elif user_lower in ("no", "n", "cancel", "stop", "abort", "nope"):
            agent.stage = agent.STAGE_IDLE
            return "## ❌ Plan Cancelled\n\nNo problem! What else would you like to analyze?\n\n*Click an example or type a new question.*"
        else:
            return """## ⏳ Waiting for Approval

Please respond with:
- **✅ Yes** (or click the button) to approve
- **❌ No** (or click the button) to cancel

*Or type `yes` / `no`*"""
    
    if agent.stage == agent.STAGE_AWAITING_SQL_APPROVAL:
        if user_lower in ("yes", "y", "run", "execute", "ok", "okay", "sure"):
            return handle_sql_approved()
        elif user_lower in ("no", "n", "cancel", "stop", "abort", "nope"):
            agent.stage = agent.STAGE_IDLE
            return "## ❌ Query Cancelled\n\nNo worries! What else would you like to analyze?\n\n*Click an example or type a new question.*"
        else:
            return """## ⏳ Waiting for SQL Approval

Please respond with:
- **✅ Yes** (or click the button) to run the query
- **❌ No** (or click the button) to cancel

*Or type `yes` / `no`*"""
    
    if agent.stage == agent.STAGE_AWAITING_SLOT:
        return handle_slot_response(user_message)
    
    if agent.stage == agent.STAGE_AWAITING_CLARIFICATION:
        return handle_clarification_response(user_message)
    
    return process_new_query(user_message)


def process_new_query(query: str) -> str:
    """Process a new analytical query"""
    global agent
    
    # Security check
    if detect_sql_injection(query):
        return """## 🚫 Security Alert

That looks like a potential SQL injection attempt.

I only run safe, pre-built SELECT queries. Please rephrase your question in plain English.

**Example:** *"Show me trips in January 2022"*"""
    
    # Check for unsupported queries
    unsupported = detect_unsupported_query(query)
    if unsupported:
        return f"""## ⚠️ Not Supported Yet

{unsupported}

### 💡 What I *can* analyze:
- 🚕 **Trips** — Count rides over time
- 💰 **Fares** — Average or total fares
- 💵 **Tips** — Tip trends
- 🏢 **Vendors** — Company activity

**Try:** *"Show trips in January 2022 by week"*"""
    
    # Check for "busier" clarification
    if needs_busier_clarification(query):
        agent.stage = agent.STAGE_AWAITING_CLARIFICATION
        agent.pending_clarification = "busier"
        agent.last_query = query
        return """## ❓ Quick Clarification

When you say "busier", what do you mean?

| Option | Meaning |
|--------|---------|
| **1** | More trips (ride count) |
| **2** | More revenue (total fares) |
| **3** | Higher average fare per trip |

*Type `1`, `2`, or `3`*"""
    
    # Reset state but preserve context
    last_context = agent.state.get("_last_query_context")
    agent.state = reset_session()
    agent.state["_last_query_context"] = last_context
    agent.last_query = query
    
    # Semantic rewrite
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
        return """## ❌ Out of Scope

I can only analyze **NYC Yellow Taxi data from 2022**.

### 💡 Try asking about:
- Trip counts
- Fare amounts
- Tip trends  
- Vendor activity

**Example:** *"Average fares in Q1 2022 by week"*"""
    
    intent = route.get("intent", "unknown")
    
    if intent not in SUPPORTED_INTENTS:
        return """## ❓ Not Sure What You Mean

I can help with these types of analysis:

| Type | Example Question |
|------|------------------|
| 🚕 **Trips** | "How many trips in January?" |
| 💰 **Fares** | "Average fares in Q1 by week" |
| 💵 **Tips** | "Total tips in summer 2022" |
| 🏢 **Vendors** | "Inactive vendors in March" |

*Try rephrasing or click an example button below!*"""
    
    agent.state["intent"] = intent
    
    # Check for missing slots
    missing = missing_slots(agent.state, intent)
    
    if missing:
        agent.pending_slot = missing[0]
        agent.stage = agent.STAGE_AWAITING_SLOT
        return format_slot_prompt(missing[0], agent.state)
    
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
        return f"""## ⚠️ Invalid Input

**Error:** {e}

---

{format_slot_prompt(slot, agent.state)}"""
    
    # Check for more missing slots
    intent = agent.state["intent"]
    missing = missing_slots(agent.state, intent)
    
    if missing:
        agent.pending_slot = missing[0]
        return format_slot_prompt(missing[0], agent.state)
    
    agent.pending_slot = None
    agent.stage = agent.STAGE_IDLE
    return show_plan()


def handle_clarification_response(response: str) -> str:
    """Handle clarification responses"""
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
            return """## ⚠️ Invalid Option

Please type `1`, `2`, or `3` to clarify what "busier" means:

| Option | Meaning |
|--------|---------|
| **1** | More trips |
| **2** | More revenue |
| **3** | Higher average fare |"""
        
        agent.pending_clarification = None
        agent.stage = agent.STAGE_IDLE
        
        query = agent.last_query
        rewrite = semantic_rewrite(agent.model, query)
        rewritten = (rewrite.get("rewritten") or query).strip()
        extract_slots_from_text(agent.state, rewritten)
        
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
    
    try:
        from symbiote_lite.slots import validate_dates_state
        validate_dates_state(agent.state)
    except Exception as e:
        agent.state["start_date"] = None
        agent.state["end_date"] = None
        agent.pending_slot = "start_date"
        agent.stage = agent.STAGE_AWAITING_SLOT
        return f"""## ⚠️ Date Issue

**Error:** {e}

Let's fix this — please provide a valid start date.

---

{format_slot_prompt('start_date', agent.state)}"""
    
    if not validate_all_slots(agent.state):
        agent.stage = agent.STAGE_IDLE
        return "## ⚠️ Validation Error\n\nSomething went wrong. Please type `reset` and try again."
    
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
            return """## ⚠️ No Results

The query returned 0 rows.

**💡 Suggestions:**
- Try a wider date range
- Check if the dates are in 2022
- Simplify your question

*Click an example button to try a known-working query!*"""
        
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
        return f"""## ❌ Query Failed

**Error:** {e}

This might be a temporary issue. Please try:
- Type `reset` to start fresh
- Click an example button
- Simplify your question"""


# ============================================================
# GRADIO UI
# ============================================================

def create_interface():
    """Create and configure the Gradio interface"""
    
    with gr.Blocks(title="Symbiote Lite Analyst") as demo:
        
        # Header
        gr.HTML(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
            <div>
                <h1 style="margin: 0; font-size: 24px;">🔬 Symbiote Lite Analyst</h1>
                <p style="margin: 4px 0 0 0; color: #6b7280; font-size: 14px;">
                    Human-in-the-loop AI analyst for NYC Taxi Data ({DATASET_YEAR})
                </p>
            </div>
            <div>
                <span class="status-badge badge-green">⚡ {agent.get_model_status()}</span>
                <span class="status-badge badge-blue">🔒 Safe SQL Only</span>
            </div>
        </div>
        """)
        
        # Chatbot
        chatbot = gr.Chatbot(
            elem_id="chatbot",
            value=[{"role": "assistant", "content": WELCOME_MESSAGE}],
            height=450,
        )
        
        # Input row
        with gr.Row():
            msg = gr.Textbox(
                elem_id="msg-input",
                placeholder="Ask me about NYC taxi trips... (e.g., 'show trips in January 2022 by week')",
                show_label=False,
                lines=1,
                scale=5,
            )
            submit_btn = gr.Button("Send", variant="primary", scale=1)
        
        # Quick action buttons
        gr.HTML("<p style='margin: 12px 0 8px 0; font-weight: 600; font-size: 14px;'>⚡ Quick Actions</p>")
        
        with gr.Row():
            yes_btn = gr.Button("✅ Yes", variant="primary", elem_classes="quick-btn quick-btn-yes")
            no_btn = gr.Button("❌ No", variant="stop", elem_classes="quick-btn quick-btn-no")
            help_btn = gr.Button("❓ Help", elem_classes="quick-btn")
            reset_btn = gr.Button("🔄 Reset", elem_classes="quick-btn")
            clear_btn = gr.Button("🗑️ Clear Chat", elem_classes="quick-btn")
        
        # Example queries
        gr.HTML("<p style='margin: 16px 0 8px 0; font-weight: 600; font-size: 14px;'>💡 Example Queries (click to try)</p>")
        
        with gr.Row(elem_classes="example-row"):
            ex1 = gr.Button("🚕 Trips in Jan 2022 by week", elem_classes="example-btn")
            ex2 = gr.Button("💰 Avg fares in Feb by day", elem_classes="example-btn")
            ex3 = gr.Button("💵 Total tips in Q2 by month", elem_classes="example-btn")
            ex4 = gr.Button("🏢 Inactive vendors in March", elem_classes="example-btn")
        
        # Workflow info
        gr.HTML("""
        <div style="margin-top: 16px; padding: 12px; background: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0;">
            <p style="margin: 0 0 8px 0; font-weight: 600; font-size: 13px;">🔄 Workflow</p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                <span class="workflow-step"><span class="step-number">1</span> Ask Question</span>
                <span class="workflow-step"><span class="step-number">2</span> Review Plan</span>
                <span class="workflow-step"><span class="step-number">3</span> Approve SQL</span>
                <span class="workflow-step"><span class="step-number">4</span> See Results</span>
            </div>
        </div>
        """)
        
        # Event handlers
        def respond(message: str, chat_history: List):
            if not message.strip():
                return "", chat_history
            
            chat_history = chat_history + [{"role": "user", "content": message}]
            response = process_message(message, chat_history)
            chat_history = chat_history + [{"role": "assistant", "content": response}]
            
            return "", chat_history
        
        def quick_action(action: str, chat_history: List):
            chat_history = chat_history + [{"role": "user", "content": action}]
            response = process_message(action, chat_history)
            chat_history = chat_history + [{"role": "assistant", "content": response}]
            return chat_history
        
        def clear_chat():
            agent.reset()
            return [{"role": "assistant", "content": WELCOME_MESSAGE}], ""
        
        def use_example(example_text: str, chat_history: List):
            return respond(example_text, chat_history)
        
        # Bindings
        msg.submit(respond, [msg, chatbot], [msg, chatbot])
        submit_btn.click(respond, [msg, chatbot], [msg, chatbot])
        
        yes_btn.click(lambda h: quick_action("yes", h), [chatbot], [chatbot])
        no_btn.click(lambda h: quick_action("no", h), [chatbot], [chatbot])
        help_btn.click(lambda h: quick_action("help", h), [chatbot], [chatbot])
        reset_btn.click(lambda h: quick_action("reset", h), [chatbot], [chatbot])
        clear_btn.click(clear_chat, outputs=[chatbot, msg])
        
        ex1.click(lambda h: use_example("show trips in January 2022 by week", h), [chatbot], [msg, chatbot])
        ex2.click(lambda h: use_example("average fares in February 2022 by day", h), [chatbot], [msg, chatbot])
        ex3.click(lambda h: use_example("total tips in Q2 2022 by month", h), [chatbot], [msg, chatbot])
        ex4.click(lambda h: use_example("which vendors were inactive in March 2022", h), [chatbot], [msg, chatbot])
    
    return demo


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    try:
        import tabulate
    except ImportError:
        print("Installing tabulate...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tabulate", "-q"])
    
    print(f"Starting Symbiote Lite Analyst...")
    print(f"Gradio version: {gr.__version__}")
    
    demo = create_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        css=CUSTOM_CSS,
    )
