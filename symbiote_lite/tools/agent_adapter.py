"""
Agent adapter for MCP.

Bridges MCP ↔ non-interactive agent core.
This is the entry point for external MCP clients.
"""

from symbiote_lite.tools.executor import DirectToolExecutor


class MCPAgentAdapter:
    """
    Adapter that allows MCP to call Symbiote Lite safely.
    
    This adapter:
    1. Wraps the DirectToolExecutor for raw SQL execution
    2. Can delegate to agent_core.analyze_query() for full NL analysis
    """

    def __init__(self):
        self.executor = DirectToolExecutor()

    def analyze(self, query: str) -> dict:
        """
        Run natural language analysis using the agent core.
        Imports lazily to avoid circular imports.
        """
        from symbiote_lite.agent_core import analyze_query
        return analyze_query(query)

    def execute_sql(self, sql: str) -> dict:
        """
        Execute SQL through the MCP boundary.
        """
        return self.executor.execute_sql(sql)
