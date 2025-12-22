"""
Agent adapter for MCP.

Bridges MCP → non-interactive agent core.
"""

from symbiote_lite.agent_core import analyze_query
from symbiote_lite.tools.executor import DirectToolExecutor


class MCPAgentAdapter:
    """
    Adapter that allows MCP to call Symbiote Lite safely.
    """

    def __init__(self):
        self.executor = DirectToolExecutor()

    def analyze(self, query: str) -> dict:
        """
        Run natural language analysis using the agent core.
        """
        return analyze_query(query)
