"""
Non-interactive core logic for Symbiote Lite.

This module:
- Accepts a natural language query
- Returns structured results
- Contains NO input() or print()
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
from .sql.executor import execute_sql_query


def analyze_query(query: str) -> Dict[str, Any]:
    """
    Pure agent entrypoint for MCP / API usage.
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
    df = execute_sql_query(sql)

    return {
        "success": True,
        "intent": state["intent"],
        "sql": sql,
        "rows": df.to_dict(orient="records"),
        "row_count": len(df),
    }
