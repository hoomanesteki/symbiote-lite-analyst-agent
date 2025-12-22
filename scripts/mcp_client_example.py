"""
Minimal MCP client test — FastMCP (manual server)

This proves:
- MCP server is reachable
- Tools can be discovered
- Tools can be called
"""

import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client


async def main():
    # Connect to already-running FastMCP server
    async with stdio_client() as (read, write):
        async with ClientSession(read, write) as session:

            tools = await session.list_tools()
            print("Available tools:")
            for tool in tools:
                print("-", tool.name)

            result = await session.call_tool(
                name="execute_taxi_sql",
                arguments={"sql": "SELECT 1 AS test"}
            )

            print("\nTool result:")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
