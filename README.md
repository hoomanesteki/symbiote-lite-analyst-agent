# Symbiote Lite — Human-in-the-Loop Analyst Agent

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-154%2B%20passing-brightgreen.svg)](#-testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Symbiote Lite is an **agentic AI data analyst** that reasons about ambiguous business questions, asks clarifying questions, proposes analysis plans, waits for human approval, safely executes tools via MCP (Model Context Protocol), and explains results in plain English.

Unlike a chatbot that immediately answers prompts, Symbiote Lite behaves like a **responsible analytical agent** designed for enterprise analytics workflows.

---

## 🎯 Key Features

| Feature | Description |
|---------|-------------|
| **Human-in-the-Loop** | Never executes without explicit approval |
| **MCP Integration** | All tool calls go through a secure boundary |
| **Safe SQL Only** | SELECT queries only, with injection protection |
| **Ambiguity Detection** | Asks clarifying questions instead of guessing |
| **Explainable Results** | Plain English interpretation of data |
| **Comprehensive Testing** | 154+ tests covering all components |
| **Docker Ready** | Containerized deployment out of the box |
| **Make Automation** | Single-command setup, test, deploy |

---

## 🏗️ Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERACTION                         │
│  "Show me trip trends in January 2022"                          │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      REASONING LAYER                            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ Router  │→ │  Slots  │→ │  Dates  │→ │ Builder │             │
│  │ (Intent)│  │ (Parse) │  │(Validate)│  │  (SQL)  │            │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘             │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                 APPROVAL GATE (Human-in-the-Loop)               │
│  "I will count trips by week for Jan 2022. Run this? (y/n)"     │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ (only if approved)
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MCP TOOL BOUNDARY                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              DirectToolExecutor                         │    │
│  │  • Safety checks (SELECT only)                          │    │
│  │  • SQL injection detection                              │    │
│  │  • Structured output                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA LAYER                                 │
│                   SQLite: taxi_trips.sqlite                     │
└─────────────────────────────────────────────────────────────────┘
```

### MCP Integration Detail

```
┌───────────────────────────────────────────────────────────────────┐
│                     EXTERNAL CLIENTS                              │
│  ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐       │
│  │  Claude  │   │   API    │   │  Web UI   │   │   CLI    │       │
│  │ Desktop  │   │ Endpoint │   │(Streamlit)│   │  Agent   │       │
│  └────┬─────┘   └────┬─────┘   └────┬──────┘   └────┬─────┘       │
└───────┼──────────────┼──────────────┼───────────────┼─────────────┘
        │              │              │               │
        └──────────────┴──────────────┴───────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │           MCP Server (FastMCP)              │
        │  ┌───────────────────────────────────────┐  │
        │  │ Tools:                                │  │
        │  │  • analyze_taxi_data(query: str)      │  │
        │  │  • execute_taxi_sql(sql: str)         │  │
        │  └───────────────────────────────────────┘  │
        └─────────────────────┬───────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │           MCPAgentAdapter                   │
        └─────────────────────┬───────────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────────┐
        │         DirectToolExecutor                  │
        │  ┌───────────────────────────────────────┐  │
        │  │ • safe_select_only(sql)               │  │
        │  │ • detect_sql_injection(input)         │  │
        │  │ • execute_sql_query(sql)              │  │
        │  └───────────────────────────────────────┘  │
        └─────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
symbiote-lite-analyst-agent/
│
├── 📂 scripts/                    # Entry points & utilities
│   ├── __init__.py
│   ├── run_agent.py              # Interactive CLI entry point
│   ├── mcp_server.py             # MCP server for external clients
│   ├── mcp_client_example.py     # Example MCP client
│   ├── create_sample_db.py       # Generate test data
│   └── test_mcp_integration.py   # MCP integration tests
│
├── 📂 symbiote_lite/              # Core package
│   ├── __init__.py
│   ├── agent.py                  # Main agent loop (interactive)
│   ├── agent_core.py             # Non-interactive core logic
│   ├── router.py                 # Intent classification
│   ├── slots.py                  # Slot filling & validation
│   ├── dates.py                  # Date parsing & validation
│   ├── explain.py                # Result explanation
│   │
│   ├── 📂 sql/                    # SQL components
│   │   ├── __init__.py
│   │   ├── builder.py            # SQL query generation
│   │   ├── executor.py           # Low-level SQL execution
│   │   └── safety.py             # SQL safety checks
│   │
│   └── 📂 tools/                  # MCP tool layer
│       ├── __init__.py
│       ├── executor.py           # MCP tool executor (boundary)
│       └── agent_adapter.py      # MCP ↔ Agent bridge
│
├── 📂 tests/                      # Test suite (154+ tests)
│   ├── __init__.py
│   ├── conftest.py               # Shared fixtures
│   ├── test_agent_smoke.py       # Import & smoke tests
│   ├── test_dates.py             # Date parsing tests
│   ├── test_router.py            # Intent routing tests
│   ├── test_slots.py             # Slot filling tests
│   ├── test_sql_builder.py       # SQL generation tests
│   ├── test_sql_executor.py      # SQL execution tests
│   ├── test_sql_safety.py        # Security tests
│   ├── test_explain.py           # Explanation tests
│   └── test_mcp.py               # MCP integration tests
│
├── 📂 data/
│   └── taxi_trips.sqlite         # Sample NYC taxi data (2022)
│
├── 📄 Makefile                    # Build automation (40+ commands)
├── 📄 Dockerfile                  # Container definition
├── 📄 docker-compose.yml          # Container orchestration
├── 📄 environment.yml             # Conda environment
├── 📄 pyproject.toml              # Python project config
├── 📄 pytest.ini                  # Test configuration
├── 📄 .gitignore
├── 📄 LICENSE
└── 📄 README.md
```

---

## 🚀 Quick Start

### Option 1: Using Make (Recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/symbiote-lite-analyst-agent.git
cd symbiote-lite-analyst-agent

# Full setup (install deps + create database)
make setup

# Run the agent
make run
```

### Option 2: Manual Setup

```bash
# Create conda environment
conda env create -f environment.yml
conda activate symbiote-lite

# Or using pip
pip install pandas numpy python-dotenv mcp openai pytest

# Create sample database
python -m scripts.create_sample_db

# Run the agent
python -m scripts.run_agent
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

## 📋 Makefile Commands Reference

Run `make help` to see all available commands:

### Setup & Installation

| Command | Description |
|---------|-------------|
| `make setup` | Full setup: install deps + create database |
| `make install` | Install production dependencies |
| `make install-dev` | Install development dependencies |
| `make conda-create` | Create conda environment |
| `make conda-update` | Update conda environment |
| `make conda-lock` | Create lock file for all platforms |

### Running

| Command | Description |
|---------|-------------|
| `make run` | Run interactive agent |
| `make server` | Start MCP server |
| `make db` | Create sample database |
| `make db-reset` | Delete and recreate database |

### Testing

| Command | Description |
|---------|-------------|
| `make test` | Run all tests |
| `make test-fast` | Run tests (skip slow ones) |
| `make test-cov` | Run tests with coverage report |
| `make test-mcp` | Run MCP integration tests |
| `make test-all` | Run all tests including MCP |

### Code Quality

| Command | Description |
|---------|-------------|
| `make lint` | Run linter (ruff) |
| `make lint-fix` | Run linter with auto-fix |
| `make format` | Format code |
| `make typecheck` | Run type checker (mypy) |
| `make check` | Run all quality checks |

### Docker

| Command | Description |
|---------|-------------|
| `make docker-build` | Build Docker image |
| `make docker-run` | Run agent in container |
| `make docker-server` | Run MCP server in container |
| `make docker-test` | Run tests in container |
| `make docker-shell` | Open shell in container |

### Workflow

| Command | Description |
|---------|-------------|
| `make pre-commit` | Run before committing (format, lint, test) |
| `make dev` | Watch mode: run tests on file changes |
| `make clean` | Remove Python cache files |
| `make clean-all` | Remove all generated files |

---

## 🧪 Testing

### Test Suite Overview

| Test File | Description | Tests |
|-----------|-------------|-------|
| `test_agent_smoke.py` | Module imports, helpers | 8 |
| `test_dates.py` | Date parsing, validation, edge cases | 25 |
| `test_router.py` | Intent classification, fallback | 18 |
| `test_slots.py` | Slot filling, normalization, typos | 22 |
| `test_sql_builder.py` | SQL generation for all intents | 16 |
| `test_sql_executor.py` | Database operations, schema | 12 |
| `test_sql_safety.py` | Injection detection, query blocking | 20 |
| `test_explain.py` | Result explanation, suggestions | 15 |
| `test_mcp.py` | MCP boundary, tool executor | 18 |
| **Total** | | **154+** |

### Running Tests

```bash
# All tests
make test

# With coverage
make test-cov

# Specific file
pytest tests/test_mcp.py -v

# Pattern matching
pytest -k "test_safety" -v

# Skip slow tests
make test-fast

# MCP only
make test-mcp
```

### Test Output Example

```
$ make test

========================= test session starts =========================
tests/test_agent_smoke.py ........                               [  5%]
tests/test_dates.py .........................                    [ 21%]
tests/test_router.py ..................                          [ 33%]
tests/test_slots.py ......................                       [ 47%]
tests/test_sql_builder.py ................                       [ 58%]
tests/test_sql_executor.py ............                          [ 66%]
tests/test_sql_safety.py ....................                    [ 79%]
tests/test_explain.py ...............                            [ 89%]
tests/test_mcp.py ..................                             [100%]

========================= 154 passed in 2.34s =========================
```

### Coverage Report

```bash
make test-cov
# Opens htmlcov/index.html with detailed coverage
```

---

## 💬 Example Interaction

```
$ make run

🧠 Symbiote Lite — NYC Taxi Analyst (2022)
🔗 MCP Mode: All SQL execution goes through DirectToolExecutor

Ask a question: show trips in January 2022 by week

============================================================
🧠 EXECUTION PLAN
============================================================
📌 Task: Count trips over time
📅 Period: 2022-01-01 to 2022-02-01 (exclusive)
⏱️  Granularity: weekly
💾 Expected output: ~4 rows
🔗 Execution: via MCP DirectToolExecutor
============================================================

Does this look correct? (yes/no): yes

📊 What this query does:
   Count how many taxi trips occurred in each time bucket

SQL:
SELECT STRFTIME('%Y-%W', pickup_datetime) AS week, COUNT(*) AS trips
FROM taxi_trips
WHERE pickup_datetime >= '2022-01-01'
  AND pickup_datetime < '2022-02-01'
GROUP BY 1
ORDER BY 1;

Run query? (yes/no): yes
⏳ Running query via MCP tool executor...
✅ Query complete (executed via MCP)!

      week  trips
0  2022-00    170
1  2022-01    785
2  2022-02    930
3  2022-03    943

Done. Returned 4 rows.

💡 You might also want to:
   1. Compare this to another period
   2. See which vendors drove these trips
   3. Check fare trends for the same period
```

---

## 🔧 MCP Server

### Start the Server

```bash
make server
```

### Available Tools

| Tool | Description |
|------|-------------|
| `analyze_taxi_data(query)` | Natural language → SQL → Results |
| `execute_taxi_sql(sql)` | Direct SQL (SELECT only) |

### Claude Desktop Integration

Add to `~/.config/claude/config.json`:

```json
{
  "mcpServers": {
    "symbiote-lite": {
      "command": "python",
      "args": ["-m", "scripts.mcp_server"],
      "cwd": "/path/to/symbiote-lite-analyst-agent"
    }
  }
}
```

---

## 🐳 Docker

```bash
# Build
make docker-build

# Run interactively
make docker-run

# Run MCP server
make docker-server

# Run tests
make docker-test

# Shell access
make docker-shell

# Docker Compose
docker-compose up -d        # Start
docker-compose logs -f      # Logs
docker-compose down         # Stop
```

---

## 📊 Supported Analyses

| Intent | Example Query |
|--------|---------------|
| Trip frequency | "show trips in April by week" |
| Fare trends | "average fares in Q2 by month" |
| Tip trends | "total tips in summer by week" |
| Vendor activity | "which vendors were inactive in Nov" |
| Data samples | "show me 50 sample trips" |

---

## 🔒 Security

### SQL Injection Protection

```python
"' OR '1'='1"           # ❌ Blocked
"UNION SELECT *"        # ❌ Blocked
"; DROP TABLE"          # ❌ Blocked
```

### MCP Boundary

```
Agent → DirectToolExecutor → safe_select_only() → SQL
         ↑
    All execution passes through here
```

---

## 🔄 Development Workflow

```bash
# Setup
make install-dev
make db

# Daily work
make run            # Test changes
make test           # Verify
make lint           # Style check

# Before commit
make pre-commit     # Format + Lint + Test

# Release
make conda-lock     # Lock dependencies
make docker-build   # Build container
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| pandas | Data manipulation |
| numpy | Numerical operations |
| python-dotenv | Environment management |
| mcp | Model Context Protocol |
| openai | LLM routing (optional) |
| pytest | Testing |

---

## 📜 License

MIT License — See [LICENSE](LICENSE)

---

<div align="center">

**Symbiote Lite** — Agentic AI analyst with human-in-the-loop control and MCP integration.

[Report Bug](https://github.com/yourusername/symbiote-lite-analyst-agent/issues) · [Request Feature](https://github.com/yourusername/symbiote-lite-analyst-agent/issues)

</div>
