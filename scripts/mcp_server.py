"""
MCP Server for Symbiote Lite

This server exposes two tools via MCP:
1. analyze_taxi_data - Full natural language analysis
2. execute_taxi_sql - Direct SQL execution (SELECT only)

Run with: python -m scripts.mcp_server
"""

from mcp.server.fastmcp import FastMCP
from symbiote_lite.tools.agent_adapter import MCPAgentAdapter

# Create the MCP server
mcp = FastMCP("symbiote-lite")

# Create a single adapter instance
agent_adapter = MCPAgentAdapter()


@mcp.tool()
def analyze_taxi_data(query: str) -> dict:
    """
    Analyze NYC taxi data using natural language.
    
    Args:
        query: Natural language question about taxi data (2022 only)
        
    Returns:
        dict with success, intent, sql, rows, row_count
        
    Examples:
        - "show trips in January 2022 by week"
        - "what were the average fares in summer 2022"
        - "which vendors were least active in Q2"
    """
    return agent_adapter.analyze(query)


@mcp.tool()
def execute_taxi_sql(sql: str) -> dict:
    """
    Execute a SELECT-only SQL query against the taxi dataset.
    
    Args:
        sql: SQL query (must be SELECT or WITH only)
        
    Returns:
        dict with success, rows, row_count, columns
        
    Security:
        - Only SELECT queries allowed
        - No mutations (INSERT, UPDATE, DELETE, etc.)
        - SQL injection patterns are blocked
    """
    return agent_adapter.execute_sql(sql)


if __name__ == "__main__":
    mcp.run()
