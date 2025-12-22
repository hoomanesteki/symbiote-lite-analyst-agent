"""
Tool executors for Symbiote Lite.

This layer is intentionally:
- LLM-free
- Agent-free
- Safe to expose via MCP
"""

from symbiote_lite.sql.executor import execute_sql_query
from symbiote_lite.sql.safety import safe_select_only


class DirectToolExecutor:
    """
    Executes tools directly (no LLM, no orchestration).

    Used by:
    - MCP server
    - Future API endpoints
    """

    def execute_sql(self, sql: str) -> dict:
        """
        Execute a safe SELECT-only SQL query.

        Args:
            sql: SQL query string (must be SELECT-only)

        Returns:
            dict with rows, columns, row_count
        """
        # 1. Safety check
        safe_select_only(sql)

        # 2. Execute
        df = execute_sql_query(sql)

        # 3. Normalize output
        return {
            "success": True,
            "rows": df.to_dict(orient="records") if df is not None else [],
            "row_count": len(df) if df is not None else 0,
            "columns": list(df.columns) if df is not None else [],
        }
