# Symbiote Lite

A human-in-the-loop AI analyst agent. It reasons about your question, asks for clarification when needed, proposes a plan, waits for your approval, then runs safe SQL queries.

Built with MCP (Model Context Protocol) for clean tool boundaries.

---

## What it does

```
You: "show me trip trends in January 2022"
        ↓
Agent reasons → fills slots → builds SQL
        ↓
"I'll count trips by week for Jan 2022. Run? (y/n)"
        ↓
You approve → query runs → results + explanation
```

Key behaviors:
- **Never executes without approval:** always asks first
- **SELECT only:** can't modify data
- **Detects ambiguity:** asks clarifying questions instead of guessing

---

## Data

Uses NYC taxi trip data (2022) from Google BigQuery public datasets:

**BigQuery source:** [bigquery-public-data.new_york_taxi_trips](https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=new_york_taxi_trips&page=dataset)

Locally stored in SQLite: `data/taxi_trips.sqlite`

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Your Question                      │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  Reasoning Layer                                │
│  Router → Slots → Dates → SQL Builder           │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  Approval Gate                                  │
│  "Does this look correct? (y/n)"                │
└──────────────────────┬──────────────────────────┘
                       ↓ (only if approved)
┌─────────────────────────────────────────────────┐
│  MCP Tool Executor                              │
│  • Safety checks (SELECT only)                  │
│  • SQL injection detection                      │
│  • Execute & return results                     │
└──────────────────────┬──────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────┐
│  SQLite / BigQuery                              │
└─────────────────────────────────────────────────┘
```

---

## Project Structure

```
symbiote-lite-analyst-agent/
├── scripts/
│   ├── run_agent.py          # CLI entry point
│   ├── gradio_app.py         # Web UI entry point
│   ├── mcp_server.py         # MCP server
│   └── create_sample_db.py   # Generate test data
│
├── symbiote_lite/
│   ├── agent.py              # Main agent loop
│   ├── router.py             # Intent classification
│   ├── slots.py              # Slot filling
│   ├── dates.py              # Date parsing
│   ├── explain.py            # Result explanation
│   ├── sql/
│   │   ├── builder.py        # SQL generation
│   │   ├── executor.py       # SQL execution
│   │   └── safety.py         # Injection protection
│   └── tools/
│       └── executor.py       # MCP tool boundary
│
├── tests/                    # 154+ tests
├── data/
│   └── taxi_trips.sqlite     # Sample data (2022)
│
├── Makefile
├── Dockerfile
└── environment.yml
```

---

## 🚀 Quick Start

### Option 1: Using Make (Recommended)

```bash
# Clone the repository
git clone https://github.com/hoomanesteki/symbiote-lite-analyst-agent.git
cd symbiote-lite-analyst-agent

# Full setup (install deps + create database)
make setup

# Run the CLI agent
make run

# Run the Web UI
make run-ui
```

### Option 2: Manual Setup

```bash
# Create conda environment
conda env create -f environment.yml
conda activate symbiote-lite

# Or using pip
pip install pandas numpy python-dotenv mcp openai pytest gradio tabulate

# Create sample database
python -m scripts.create_sample_db

# Run the CLI agent
python -m scripts.run_agent

# Run the Web UI
python -m scripts.gradio_app
```

### Option 3: Using Docker

```bash
# Build and run
make docker-build
make docker-run

# Or with docker-compose
docker-compose up agent
```

---

## 🌐 Web UI (Gradio)

The agent includes a web-based chat interface built with Gradio.

### Running the Web UI

```bash
# Using Make
make run-ui          # Local only (http://localhost:7860)
make run-ui-public   # Get shareable public URL

# Or directly
python -m scripts.gradio_app
```

Then open **http://localhost:7860** in your browser.

### Web UI Features

- **Chat-based interface:** Natural conversation flow
- **Same approval workflow:** Plan → SQL → Execute
- **Example queries:** Click to try pre-built questions
- **Works with or without LLM:** Falls back to deterministic routing

### Screenshot

```
┌─────────────────────────────────────────────────────────┐
│  🔬 Symbiote Lite Analyst Agent                         │
│  ───────────────────────────────────────────────────    │
│                                                         │
│  You: show trips in January 2022 by week                │
│                                                         │
│  Agent: 🧠 EXECUTION PLAN                               │
│         Task: Count trips over time                     │
│         Period: 2022-01-01 to 2022-02-01                │
│         Granularity: weekly                             │
│                                                         │
│         Does this look correct? Reply yes or no.        │
│                                                         │
│  You: yes                                               │
│                                                         │
│  Agent: ✅ Query Results                                │
│         | week    | trips |                             │
│         |---------|-------|                             │
│         | 2022-00 | 170   |                             │
│         | 2022-01 | 785   |                             │
│         | 2022-02 | 930   |                             │
│                                                         │
│  [Type a message...]                         [Send]     │
└─────────────────────────────────────────────────────────┘
```

---

## Example (CLI)

```
Ask: show trips in January 2022 by week

🧠 EXECUTION PLAN
Task: Count trips over time
Period: 2022-01-01 to 2022-02-01
Granularity: weekly

Does this look correct? (yes/no): yes

SQL:
SELECT STRFTIME('%Y-%W', pickup_datetime) AS week, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '2022-01-01'
  AND pickup_datetime < '2022-02-01'
GROUP BY 1 ORDER BY 1;

Run query? (yes/no): yes

      week  trips
0  2022-00    170
1  2022-01    785
2  2022-02    930
3  2022-03    943
```

---

## Supported Queries

| Type | Example |
|------|---------|
| Trip counts | "trips in April by week" |
| Fare analysis | "average fares in Q2 by month" |
| Tip trends | "total tips in summer" |
| Vendor activity | "which vendors were inactive in Nov" |
| Samples | "show me 50 sample trips" |

---

## Makefile Commands

```bash
make setup           # Install dependencies + create database
make run             # Run CLI agent
make run-ui          # Run Gradio web UI (localhost:7860)
make run-ui-public   # Run web UI with public shareable URL
make test            # Run all tests
make test-cov        # Run tests with coverage
make test-fast       # Skip slow tests
make docker-build    # Build Docker image
make docker-run      # Run in Docker
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Enables LLM routing (optional) | None |
| `SYMBIOTE_DB_PATH` | Path to SQLite database | `data/taxi_trips.sqlite` |
| `SYMBIOTE_MODEL` | OpenAI model name | `gpt-4` |

---

## Testing

```bash
make test          # all tests
make test-cov      # with coverage
make test-fast     # skip slow ones
```

---

## License

MIT
