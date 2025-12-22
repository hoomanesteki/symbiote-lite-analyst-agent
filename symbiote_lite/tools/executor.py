"""
Tool executors for Symbiote Lite.

This layer is intentionally:
- LLM-free
- Agent-free
- Safe to expose via MCP

This is the MCP BOUNDARY - all tool execution goes through here.
"""

import pandas as pd
from symbiote_lite.sql.executor import execute_sql_query
from symbiote_lite.sql.safety import safe_select_only


class DirectToolExecutor:
    """
    Executes tools directly (no LLM, no orchestration).

    Used by:
    - MCP server
    - Agent (via MCPAgentAdapter)
    - Future API endpoints

    This class represents the MCP tool boundary.
    The agent NEVER executes SQL directly - it always goes through this executor.
    """

    def execute_sql(self, sql: str) -> dict:
        """
        Execute a safe SELECT-only SQL query.

        Args:
            sql: SQL query string (must be SELECT-only)

        Returns:
            dict with success, rows, columns, row_count, dataframe
        """
        # 1. Safety check (raises ValueError if unsafe)
        safe_select_only(sql)

        # 2. Execute via the low-level executor
        df = execute_sql_query(sql)

        # 3. Return structured result (MCP-style)
        return {
            "success": True,
            "rows": df.to_dict(orient="records") if df is not None else [],
            "row_count": len(df) if df is not None else 0,
            "columns": list(df.columns) if df is not None else [],
            "dataframe": df,  # Keep DataFrame for agent convenience
        }

    def execute_sql_to_dataframe(self, sql: str) -> pd.DataFrame:
        """
        Convenience method that returns just the DataFrame.
        Still goes through the MCP boundary (execute_sql).
        """
        result = self.execute_sql(sql)
        return result.get("dataframe", pd.DataFrame())
