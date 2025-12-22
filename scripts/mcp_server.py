"""
MCP Server Example for Symbiote Lite.

This file shows how to integrate Symbiote Lite with the Model Context Protocol (MCP).
MCP allows AI assistants to securely access tools and data sources.

To use this, you would typically:
1. Install an MCP server framework (e.g., @modelcontextprotocol/server-python)
2. Register this as a tool provider
3. Connect it to your AI assistant

For more info: https://modelcontextprotocol.io/
"""

from typing import Any, Dict, List
import json

from symbiote_lite import SymbioteAgent
from symbiote_lite.sql import execute_sql_query, safe_select_only, set_mcp_handler


# =============================================================================
# MCP Tool Definitions
# =============================================================================
MCP_TOOLS = [
    {
        "name": "analyze_taxi_data",
        "description": (
            "Analyze NYC Yellow Taxi data from 2022 using natural language. "
            "Supports: trip counts, fare trends, tip trends, vendor analysis. "
            "Example: 'show trips in summer 2022 by week'"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query about taxi data"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "execute_taxi_sql",
        "description": (
            "Execute a safe, SELECT-only SQL query against the taxi_trips table. "
            "Only SELECT queries are allowed. "
            "Available columns: pickup_datetime, dropoff_datetime, vendor_id, "
            "fare_amount, tip_amount, total_amount"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL SELECT query"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "get_taxi_schema",
        "description": "Get the schema of the taxi_trips table",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


# =============================================================================
# MCP Handler Class
# =============================================================================
class SymbioteMCPHandler:
    """
    MCP handler for Symbiote Lite.
    
    This class handles MCP tool calls and routes them to the appropriate
    Symbiote Lite functions.
    """
    
    def __init__(self, database_executor=None):
        """
        Initialize the MCP handler.
        
        Args:
            database_executor: Optional database executor for SQL queries.
                              If not provided, you must set one via set_mcp_handler().
        """
        self.agent = SymbioteAgent(use_llm=True)
        
        if database_executor:
            set_mcp_handler(database_executor)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return list of available MCP tools."""
        return MCP_TOOLS
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle an MCP tool call.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool result as dict with 'success', 'result', and optionally 'error'
        """
        try:
            if tool_name == "analyze_taxi_data":
                return self._handle_analyze(arguments.get("query", ""))
            
            elif tool_name == "execute_taxi_sql":
                return self._handle_sql(arguments.get("sql", ""))
            
            elif tool_name == "get_taxi_schema":
                return self._handle_schema()
            
            else:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _handle_analyze(self, query: str) -> Dict[str, Any]:
        """Handle analyze_taxi_data tool call."""
        result = self.agent.process_query(query)
        
        if result["success"]:
            # Convert DataFrame to JSON-serializable format
            df = result["result"]
            return {
                "success": True,
                "result": {
                    "intent": result["intent"],
                    "sql": result["sql"],
                    "data": df.to_dict(orient="records") if df is not None else [],
                    "row_count": len(df) if df is not None else 0,
                    "suggestions": result["suggestions"]
                }
            }
        else:
            return {
                "success": False,
                "error": result["error"]
            }
    
    def _handle_sql(self, sql: str) -> Dict[str, Any]:
        """Handle execute_taxi_sql tool call."""
        try:
            # Validate SQL is safe
            safe_select_only(sql)
            
            # Execute query
            df = execute_sql_query(sql)
            
            return {
                "success": True,
                "result": {
                    "data": df.to_dict(orient="records") if df is not None else [],
                    "row_count": len(df) if df is not None else 0,
                    "columns": list(df.columns) if df is not None else []
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _handle_schema(self) -> Dict[str, Any]:
        """Handle get_taxi_schema tool call."""
        return {
            "success": True,
            "result": {
                "table": "taxi_trips",
                "columns": [
                    {"name": "pickup_datetime", "type": "TIMESTAMP", "description": "Trip start time"},
                    {"name": "dropoff_datetime", "type": "TIMESTAMP", "description": "Trip end time"},
                    {"name": "vendor_id", "type": "INTEGER", "description": "Taxi company ID"},
                    {"name": "fare_amount", "type": "DECIMAL", "description": "Base fare amount"},
                    {"name": "tip_amount", "type": "DECIMAL", "description": "Tip amount"},
                    {"name": "total_amount", "type": "DECIMAL", "description": "Total charge"},
                ],
                "constraints": {
                    "date_range": "2022-01-01 to 2022-12-31",
                    "end_date_exclusive": True
                }
            }
        }


# =============================================================================
# Example MCP Server (using stdio transport)
# =============================================================================
def create_mcp_server():
    """
    Create an MCP server instance.
    
    This is a simplified example. For production use, you would:
    1. Use a proper MCP server framework
    2. Implement proper transport handling
    3. Add authentication/authorization
    
    Example frameworks:
    - Python: @modelcontextprotocol/server-python
    - TypeScript: @modelcontextprotocol/server-typescript
    """
    import sys
    
    handler = SymbioteMCPHandler()
    
    # Simple stdin/stdout protocol (for demonstration)
    print("Symbiote Lite MCP Server started", file=sys.stderr)
    print(f"Available tools: {[t['name'] for t in handler.list_tools()]}", file=sys.stderr)
    
    for line in sys.stdin:
        try:
            request = json.loads(line.strip())
            
            if request.get("method") == "tools/list":
                response = {"tools": handler.list_tools()}
            
            elif request.get("method") == "tools/call":
                params = request.get("params", {})
                response = handler.handle_tool_call(
                    params.get("name", ""),
                    params.get("arguments", {})
                )
            
            else:
                response = {"error": f"Unknown method: {request.get('method')}"}
            
            print(json.dumps(response))
            sys.stdout.flush()
            
        except json.JSONDecodeError:
            print(json.dumps({"error": "Invalid JSON"}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.stdout.flush()


# =============================================================================
# Usage Example
# =============================================================================
if __name__ == "__main__":
    # Example: Direct usage without MCP
    print("=" * 60)
    print("Symbiote Lite MCP Handler - Direct Usage Example")
    print("=" * 60)
    
    # Create handler (without database - will need to set one)
    handler = SymbioteMCPHandler()
    
    # List available tools
    print("\nAvailable tools:")
    for tool in handler.list_tools():
        print(f"  - {tool['name']}: {tool['description'][:50]}...")
    
    # Example tool calls (these will fail without a database configured)
    print("\n" + "=" * 60)
    print("Example: Calling get_taxi_schema")
    print("=" * 60)
    
    result = handler.handle_tool_call("get_taxi_schema", {})
    print(json.dumps(result, indent=2))
    
    print("\n" + "=" * 60)
    print("To run as MCP server: python mcp_server.py --serve")
    print("=" * 60)
    
    # Check if --serve flag provided
    import sys
    if "--serve" in sys.argv:
        create_mcp_server()
