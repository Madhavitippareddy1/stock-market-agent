import asyncio
import json
import threading
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

from stock_market_agent.config import get_settings


class McpClient:
    """Small adapter for calling the shared MCP server.

    The common MCP server owns the actual tools. This project sends tool names
    and JSON payloads to that server. If the server is not running locally, the
    adapter returns a safe fallback so the UI can still start.
    """

    def __init__(self, server_url: str | None, api_key: str | None = None) -> None:
        self.server_url = server_url
        self.api_key = api_key

    @classmethod
    def from_settings(cls) -> "McpClient":
        settings = get_settings()
        return cls(server_url=settings.mcp_server_url, api_key=settings.mcp_api_key)

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with sse_client(self.server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

        if not result.content:
            return {"answer": f"MCP tool `{tool_name}` returned no content."}

        first_content = result.content[0]
        text = getattr(first_content, "text", str(first_content))

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"answer": text, "tool": tool_name}

        if isinstance(parsed, dict):
            return parsed

        return {"answer": str(parsed), "tool": tool_name}

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.server_url:
            return {
                "answer": f"MCP server URL is not configured. Tool requested: {tool_name}",
                "tool": tool_name,
                "arguments": arguments,
            }

        container: dict[str, Any] = {"result": None, "error": None}

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                container["result"] = loop.run_until_complete(
                    self._call_tool_async(tool_name, arguments)
                )
            except Exception as exc:
                container["error"] = exc
            finally:
                loop.close()

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=45)

        if thread.is_alive():
            return {
                "answer": f"MCP tool `{tool_name}` timed out.",
                "tool": tool_name,
                "arguments": arguments,
            }

        if container["error"]:
            return {
                "answer": f"MCP tool `{tool_name}` is unavailable: {container['error']}",
                "tool": tool_name,
                "arguments": arguments,
            }

        return container["result"]
