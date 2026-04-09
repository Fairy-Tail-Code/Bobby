import pytest
from unittest.mock import AsyncMock, MagicMock
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import create_sync_tool_func


def test_create_sync_tool_func():
    manager = MagicMock(spec=McpManager)
    manager.call_tool = AsyncMock(return_value="command output")

    tool_func = create_sync_tool_func(manager, "shell", "run_command")
    result = tool_func(cmd="echo hello")

    assert result == "command output"
    manager.call_tool.assert_called_once_with("shell", "run_command", {"cmd": "echo hello"})


def test_create_sync_tool_func_with_multiple_args():
    manager = MagicMock(spec=McpManager)
    manager.call_tool = AsyncMock(return_value="file content")

    tool_func = create_sync_tool_func(manager, "workspace", "read_file")
    result = tool_func(path="/tmp/test.txt", start_line=1, end_line=10)

    assert result == "file content"
    manager.call_tool.assert_called_once_with(
        "workspace", "read_file", {"path": "/tmp/test.txt", "start_line": 1, "end_line": 10}
    )