"""
OneAI Model Context Protocol (MCP) Server.
Exposes stock market analysis tools to external MCP client agents (Claude Desktop, Antigravity, etc.).
"""

import asyncio
import json
import logging
from typing import Any, Dict

from app.tools.registry import TOOLS, TOOL_MANIFESTS

logger = logging.getLogger(__name__)


def list_mcp_tools() -> Dict[str, Any]:
    """Returns all registered stock tools in MCP tool format."""
    mcp_tools = []
    for name, manifest in TOOL_MANIFESTS.items():
        mcp_tools.append({
            "name": name,
            "description": manifest.get("description", ""),
            "inputSchema": {
                "type": "object",
                "properties": manifest.get("input_schema", {}),
            }
        })
    return {"tools": mcp_tools}


async def call_mcp_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executes an MCP tool call by invoking the corresponding local function."""
    tool_func = TOOLS.get(name)
    if not tool_func:
        return {
            "content": [{"type": "text", "text": f"Error: MCP tool '{name}' not found."}],
            "isError": True,
        }

    try:
        result = await tool_func(**arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": False,
        }
    except Exception as e:
        logger.exception("MCP_TOOL_EXECUTION_ERROR | tool=%s", name)
        return {
            "content": [{"type": "text", "text": f"Error executing MCP tool '{name}': {str(e)}"}],
            "isError": True,
        }


if __name__ == "__main__":
    print(json.dumps(list_mcp_tools(), indent=2))
