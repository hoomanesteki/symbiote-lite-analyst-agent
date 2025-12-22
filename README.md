# Symbiote Lite — Human-in-the-Loop Analyst Agent

Symbiote Lite is an agentic AI data analyst that reasons about ambiguous business questions, asks clarifying questions, proposes analysis plans, waits for human approval, safely executes tools, and explains results in plain English.

Unlike a chatbot that immediately answers prompts, Symbiote Lite behaves like a responsible analytical agent designed for enterprise analytics workflows.

---

## Why Symbiote Lite Is Different

Traditional chatbots follow this pattern:

User → Prompt → Answer

Symbiote Lite follows an agentic workflow:

User → Goal → Reason → Clarify → Plan → Approval → Execute → Explain → Log

This project demonstrates modern agentic AI principles with explicit human-in-the-loop control.

---

## What the Agent Does (End-to-End)

1. Receives vague business questions  
   Examples:
   - “Why are trips higher in April?”
   - “Analyze trip frequency last quarter”
   - “Show trends in taxi usage”

2. Detects ambiguity instead of guessing  
   The agent reasons about missing information such as:
   - Time window
   - Aggregation level
   - Metric definition

3. Asks clarifying questions (Human-in-the-Loop)  
   The agent pauses and requests missing inputs before proceeding.

4. Proposes an analysis plan before acting  
   Example plan:
   - Filter trips by date range
   - Aggregate by day
   - Summarize trends

5. Generates SQL but does not execute it  
   The agent shows the SQL query and explains what it will do.

6. Waits for explicit human approval  
   The user can approve, reject, or modify the plan.

7. Executes tools safely after approval  
   - Runs SQL
   - Loads data
   - Computes aggregates

8. Explains results in plain English  
   Focuses on interpretation and business meaning.

9. Maintains session state and decisions  
   Tracks:
   - User intent
   - Clarifications
   - Approved queries
   - Executed actions

---

## Why This Is Truly Agentic (Not a Chatbot)

Feature | Chatbot | Symbiote Lite
Goal-oriented | No | Yes
Clarification | Guesses | Asks
Tool execution | No | Yes
Approval gates | No | Yes
Reasoning loop | No | Yes
Safe execution | No | Yes

---

## Tech Stack

Core:
- Python
- SQLite (local analytics)
- pandas
- Modular agent architecture

Agent Design:
- Explicit reasoning and slot filling
- Human-in-the-loop approval gates
- Tool abstraction layer
- Session state management

Optional Extensions:
- MCP (Model Context Protocol)
- Streamlit or Web UI
- Docker for reproducibility

---

## Project Structure

symbiote-lite-analyst-agent/
├── scripts/
│   ├── run_agent.py          # Entry point
│   └── mcp_client_example.py
├── symbiote_lite/
│   ├── tools/
│   │   ├── agent.py          # Core agent loop
│   │   ├── router.py         # Intent routing
│   │   ├── slots.py          # Slot filling and validation
│   │   ├── dates.py          # Date parsing and validation
│   │   └── executor.py       # Tool execution
│   └── __init__.py
├── data/
│   └── yellow_tripdata_sample.csv
├── tests/
├── environment.yml
└── README.md

---

## How to Run

From the repository root:

conda activate symbiote-lite
python -m scripts.run_agent

You should see:

🧠 Symbiote Lite — Analyst Agent  
Ask a data question:

---

## Example Interaction

User:
Show trip frequency in April

Agent:
Do you want daily or weekly aggregation?

User:
Daily

Agent:
I will aggregate daily trip counts for April 2022.
Here is the SQL I plan to run:

[SQL shown]

Run this query? (y/n)

---

## Why This Project Matters

This project demonstrates:
- Agentic reasoning, not prompt completion
- Safe and auditable analytics workflows
- Human-in-the-loop control (industry requirement)
- Clear separation between reasoning and execution
- Strong alignment with enterprise analytics practices

It bridges classical data science (SQL, pandas) with modern agentic AI system design.

---

## Skills Demonstrated

- Agentic AI architecture
- Human-in-the-loop systems
- Python packaging and modular design
- SQL analytics
- State management
- Safe tool execution
- Explainable analytics

---

## One-Sentence Summary

Symbiote Lite is an agentic AI analyst that reasons about ambiguity, asks for human approval, safely executes analysis, and explains results — not just a chatbot that answers questions.
