from mcp.server.fastmcp import FastMCP
from symbiote_lite.tools.agent_adapter import MCPAgentAdapter

mcp = FastMCP("symbiote-lite")
agent_adapter = MCPAgentAdapter()

@mcp.tool()
def analyze_taxi_data(query: str) -> dict:
    return agent_adapter.analyze(query)

@mcp.tool()
def execute_taxi_sql(sql: str) -> dict:
    return agent_adapter.executor.execute_sql(sql)

if __name__ == "__main__":
    mcp.run()
