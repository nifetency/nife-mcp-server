"""Run the curated hosted-connector tools inside the local stdio server.

The stdio server (intelligent_main.py) speaks raw JSON-RPC and builds its own tools from the
GraphQL schema. This wrapper loads the same curated tools the hosted connector offers (with
their ownership checks and trimmed results) into a private FastMCP object and exposes them
through two calls: list() and call(). Nothing listens on a network port.

Authentication: the local user's NIFE_ACCESS_TOKEN is the credential. It is handed to
tool_utils.set_stdio_token and used only when a call has no HTTP request, which is never the
case on the hosted connector.

Needs the optional dependencies: pip install "nife-mcp-server[http]"
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CuratedTools:
    def __init__(self, token: Optional[str]):
        # Imported here so the stdio server still starts when mcp or httpx are not installed.
        from mcp.server.fastmcp import FastMCP

        from nife_mcp_server import tool_utils
        from nife_mcp_server.tool_registry import INSTRUCTIONS, register_all_tools

        tool_utils.set_stdio_token(token)
        self.instructions = INSTRUCTIONS
        self._mcp = FastMCP("nife-stdio")
        register_all_tools(self._mcp)

    async def list(self) -> List[Dict[str, Any]]:
        """Tool descriptors in the shape tools/list returns."""
        out: List[Dict[str, Any]] = []
        for tool in await self._mcp.list_tools():
            entry: Dict[str, Any] = {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema,
            }
            title = getattr(tool, "title", None)
            if title:
                entry["title"] = title
            if tool.annotations is not None:
                entry["annotations"] = tool.annotations.model_dump(exclude_none=True)
            out.append(entry)
        return out

    async def call(self, name: str, arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Run one tool and return a tools/call result. Errors come back as isError results."""
        try:
            result = await self._mcp.call_tool(name, arguments or {})
        except Exception as exc:  # ToolError, argument validation, anything a tool raises
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        blocks = result[0] if isinstance(result, tuple) else result
        if isinstance(blocks, dict):
            return {"content": [{"type": "text", "text": json.dumps(blocks, indent=2, default=str)}]}
        return {"content": [b.model_dump(exclude_none=True) for b in blocks]}
