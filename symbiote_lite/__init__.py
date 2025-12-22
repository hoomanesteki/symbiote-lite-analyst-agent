"""
Symbiote Lite - Human-in-the-Loop Analyst Agent

An agentic AI data analyst that:
- Reasons about ambiguous business questions
- Asks clarifying questions
- Proposes analysis plans
- Waits for human approval
- Safely executes tools via MCP
- Explains results in plain English
"""

from .agent import run_agent
from .agent_core import analyze_query
from .tools import DirectToolExecutor, MCPAgentAdapter

__all__ = [
    "run_agent",
    "analyze_query",
    "DirectToolExecutor",
    "MCPAgentAdapter",
]

__version__ = "0.1.0"
