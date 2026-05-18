import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

from infrastructure.mcp.beta_tool_bridge import _create_async_tool_func
from infrastructure.mcp.manager import McpManager


def test_create_async_tool_func_accepts_ctx_for_zero_arg_schema() -> None:
    manager = MagicMock(spec=McpManager)
    manager.call_tool = AsyncMock(return_value="current user")

    tool_func = _create_async_tool_func(
        manager,
        "gitee",
        "get_gitee_current_user",
        {"type": "object", "properties": {}, "required": []},
    )

    signature = inspect.signature(tool_func)
    assert list(signature.parameters) == ["kwargs"]
    assert signature.parameters["kwargs"].kind is inspect.Parameter.VAR_KEYWORD

    result = asyncio.run(tool_func(__ctx__=object()))

    assert result == "current user"
    manager.call_tool.assert_called_once_with("gitee", "get_gitee_current_user", {})


def test_create_async_tool_func_omits_missing_optional_args() -> None:
    manager = MagicMock(spec=McpManager)
    manager.call_tool = AsyncMock(return_value="file content")

    tool_func = _create_async_tool_func(
        manager,
        "workspace",
        "read_file",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
        },
    )

    signature = inspect.signature(tool_func)
    assert signature.parameters["path"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["start_line"].default is None
    assert signature.parameters["end_line"].default is None

    result = asyncio.run(tool_func(path="/tmp/test.txt", __ctx__=object()))

    assert result == "file content"
    manager.call_tool.assert_called_once_with(
        "workspace",
        "read_file",
        {"path": "/tmp/test.txt"},
    )
