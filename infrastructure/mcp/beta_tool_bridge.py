from __future__ import annotations

import logging
from typing import Any

from autogen.beta.tools.final.function_tool import FunctionTool, tool as beta_tool

from infrastructure.mcp.manager import McpManager

logger = logging.getLogger(__name__)


def _create_async_tool_func(
    mcp_manager: McpManager,
    server_name: str,
    tool_name: str,
):
    async def tool_func(**kwargs: Any) -> str:
        return await mcp_manager.call_tool(server_name, tool_name, kwargs)

    tool_func.__name__ = tool_name
    tool_func.__qualname__ = tool_name
    return tool_func


def build_beta_tools_for_servers(
    mcp_manager: McpManager,
    server_names: list[str],
    tool_filter: list[str] | None = None,
) -> list[FunctionTool]:
    """Build beta-compatible MCP tools for a role."""
    tools: list[FunctionTool] = []
    for server_name in server_names:
        for tool_info in mcp_manager.get_tools_for_server(server_name):
            if tool_filter and tool_info.tool_name not in tool_filter:
                continue
            tools.append(
                beta_tool(
                    _create_async_tool_func(mcp_manager, server_name, tool_info.tool_name),
                    name=tool_info.tool_name,
                    description=tool_info.description,
                    schema=tool_info.input_schema,
                )
            )
            logger.debug(
                "Built beta MCP tool '%s' from server '%s'",
                tool_info.tool_name,
                server_name,
            )
    return tools

