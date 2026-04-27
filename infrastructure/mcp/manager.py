from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from infrastructure.config import McpServerConfig, load_mcp_config, McpConfig

logger = logging.getLogger(__name__)

# Default client-side timeout for any MCP tool call.
# Acts as a safety net when the server-side timeout fails or the stdio channel stalls.
# claude_code calls can take a long time, so we set a generous default.

@dataclass
class McpToolInfo:
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]


class McpManager:
    """Manages connections to MCP servers and provides tool discovery/invocation."""

    def __init__(self,mcp_config) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._exit_stacks: dict[str, AsyncExitStack] = {}
        self._tools: dict[str, list[McpToolInfo]] = {}
        self.mcp_config: McpConfig=mcp_config

    def list_servers(self) -> list[str]:
        return list(self._sessions.keys())

    def get_tools_for_server(self, server_name: str) -> list[McpToolInfo]:
        return self._tools.get(server_name, [])

    def get_all_tools(self) -> dict[str, list[McpToolInfo]]:
        return dict(self._tools)

    def get_tool(self, server_name: str, tool_name: str) -> McpToolInfo | None:
        for tool in self.get_tools_for_server(server_name):
            if tool.tool_name == tool_name:
                return tool
        return None

    async def connect(self, config: McpServerConfig) -> None:
        """Connect to an MCP server and discover its tools."""
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
        )
        exit_stack = AsyncExitStack()
        try:
            read_stream, write_stream = await exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
        except BaseException:
            try:
                await exit_stack.aclose()
            except BaseException:
                pass
            raise

        tools_result = await session.list_tools()
        tool_infos = [
            McpToolInfo(
                server_name=config.name,
                tool_name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema or {},
            )
            for t in tools_result.tools
        ]

        self._sessions[config.name] = session
        self._exit_stacks[config.name] = exit_stack
        self._tools[config.name] = tool_infos

        logger.info(
            "Connected to MCP server '%s' with %d tools: %s",
            config.name,
            len(tool_infos),
            [t.tool_name for t in tool_infos],
        )

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """Call a tool on an MCP server and return the result as text.

        A client-side timeout prevents the swarm from hanging when the
        MCP server process stalls or the stdio channel blocks.
        """
        timeout_s=self.mcp_config.base_config.tool_timeout
        session = self._sessions.get(server_name)
        if session is None:
            raise ValueError(f"Not connected to MCP server: {server_name}")

        try:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.error(
                "MCP tool call '%s/%s' timed out after %.0fs",
                server_name, tool_name, timeout_s,
            )
            return (
                f"ERROR: MCP tool '{server_name}/{tool_name}' timed out "
                f"after {timeout_s:.0f}s. The command may still be running."
            )

        if result.content:
            return "\n".join(
                c.text if hasattr(c, "text") else str(c)
                for c in result.content
            )
        return ""

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server."""
        if server_name in self._exit_stacks:
            try:
                await self._exit_stacks[server_name].aclose()
            except BaseException:
                logger.debug("Swallowed cleanup error for MCP server '%s'", server_name, exc_info=True)
            del self._exit_stacks[server_name]
        self._sessions.pop(server_name, None)
        self._tools.pop(server_name, None)

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._sessions.keys()):
            await self.disconnect(name)