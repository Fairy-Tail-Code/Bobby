from __future__ import annotations

import logging
from typing import Any, Callable

from autogen import ConversableAgent
from autogen.tools import Tool

from infrastructure.mcp.manager import McpManager, McpToolInfo

logger = logging.getLogger(__name__)


def create_async_tool_func(
    mcp_manager: McpManager,
    server_name: str,
    tool_name: str,
) -> Callable[..., Any]:
    """Create an async wrapper function that calls an MCP tool.

    AG2's group chat runs in async context, so tool functions must be async
    to properly await MCP calls within the same event loop.
    """

    async def tool_func(**kwargs: Any) -> str:
        return await mcp_manager.call_tool(server_name, tool_name, kwargs)

    tool_func.__name__ = tool_name
    tool_func.__qualname__ = tool_name
    return tool_func


def register_tools_for_agent(
    agent: ConversableAgent,
    mcp_manager: McpManager,
    server_names: list[str],
    tool_filter: list[str] | None = None,
) -> None:
    """Register MCP tools as AG2 tools for the given agent."""
    for server_name in server_names:
        tools = mcp_manager.get_tools_for_server(server_name)
        for tool_info in tools:
            if tool_filter and tool_info.tool_name not in tool_filter:
                continue

            tool_func = create_async_tool_func(mcp_manager, server_name, tool_info.tool_name)

            ag2_tool = Tool(
                name=tool_info.tool_name,
                description=tool_info.description,
                func_or_tool=tool_func,
                parameters_json_schema=tool_info.input_schema,
            )
            ag2_tool.register_for_llm(agent)
            ag2_tool.register_for_execution(agent)
            logger.debug(
                "Registered tool '%s' from server '%s' for agent '%s'",
                tool_info.tool_name, server_name, agent.name,
            )

    logger.info(
        "Registered MCP tools for agent '%s' from servers: %s",
        agent.name, server_names,
    )
