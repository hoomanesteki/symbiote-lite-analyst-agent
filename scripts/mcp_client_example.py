"""
Minimal MCP client test — MCP 1.25.0 compatible (FINAL)

This proves:
- MCP server can be launched
- Tool can be discovered
- Tool can be called
"""

import asyncio

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, Server


async def main():
    # Create Server object (REQUIRED in MCP 1.25.0)
    server = Server(
        command=["python", "-m", "scripts.mcp_server_minimal"]
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            # List tools
            tools = await session.list_tools()
            print("TOOLS:", [t.name for t in tools])

            # Call SQL tool
            result = await session.call_tool(
                "execute_sql",
                {
                    "sql": "SELECT COUNT(*) AS trips FROM taxi_trips"
                }
            )

            print("RESULT:", result)


if __name__ == "__main__":
    asyncio.run(main())
