"""
Non-interactive core logic for Symbiote Lite.

This module:
- Accepts a natural language query
- Returns structured results
- Contains NO input() or print()
- Routes ALL execution through MCP tool boundary
"""

from typing import Dict, Any

from .router import configure_model, ask_router, semantic_rewrite
from .slots import (
    reset_session,
    extract_slots_from_text,
    validate_all_slots,
    validate_dates_state,
)
from .sql.builder import build_sql
from .sql.safety import safe_select_only
# ============================================================
# MCP INTEGRATION: Use DirectToolExecutor instead of execute_sql_query
# ============================================================
from .tools.executor import DirectToolExecutor

# Single instance of the tool executor
_tool_executor = DirectToolExecutor()


def analyze_query(query: str) -> Dict[str, Any]:
    """
    Pure agent entrypoint for MCP / API usage.
    
    All SQL execution goes through the MCP tool boundary (DirectToolExecutor).
    """
    model = configure_model()
    state = reset_session()

    # Semantic rewrite (LLM optional)
    rewrite = semantic_rewrite(model, query)
    rewritten = (rewrite.get("rewritten") or query).strip()

    extract_slots_from_text(state, rewritten)

    validate_dates_state(state)
    validate_all_slots(state)

    sql = safe_select_only(build_sql(state, state["intent"]))
    
    # ============================================================
    # MCP INTEGRATION: Execute through tool boundary
    # ============================================================
    result = _tool_executor.execute_sql(sql)

    return {
        "success": result.get("success", False),
        "intent": state["intent"],
        "sql": sql,
        "rows": result.get("rows", []),
        "row_count": result.get("row_count", 0),
        "columns": result.get("columns", []),
    }
