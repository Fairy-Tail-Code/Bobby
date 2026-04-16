import pytest
from infrastructure.mcp.manager import McpManager, McpToolInfo
from infrastructure.config import McpServerConfig


def test_mcp_manager_init():
    manager = McpManager()
    assert manager.list_servers() == []


def test_mcp_manager_tool_info():
    info = McpToolInfo(
        server_name="shell",
        tool_name="run_short_command",
        description="Run a short-lived shell command",
        input_schema={"type": "object", "properties": {"cmd": {"type": "string"}}},
    )
    assert info.server_name == "shell"
    assert info.tool_name == "run_short_command"


def test_mcp_manager_get_tools_empty():
    manager = McpManager()
    assert manager.get_tools_for_server("shell") == []


def test_mcp_manager_get_all_tools_empty():
    manager = McpManager()
    assert manager.get_all_tools() == {}


def test_mcp_manager_get_tool_not_found():
    manager = McpManager()
    assert manager.get_tool("shell", "run_short_command") is None