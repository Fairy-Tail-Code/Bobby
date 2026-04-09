# MCP 服务器集成

## openharness MCP 服务器

openharness 提供 9 个 MCP 服务器，全部基于 `FastMCP`，stdio 传输：

| 服务器 | 功能 | 关键工具 |
|--------|------|----------|
| shell_server | 命令执行 | run_command, start_command, read_command_output |
| git_server | Git 操作 | get_git_status, create_git_branch, commit_git_changes |
| browser_server | Playwright 浏览器自动化 | open_browser_session, click_browser_selector, take_browser_screenshot |
| workspace_server | 文件系统 | read_file, write_file, list_files, search_text, apply_patch |
| docker_server | Docker/Compose | 容器管理、Compose 操作 |
| database_server | 数据库操作 | SQL 执行 |
| http_api_server | HTTP 请求 | API 测试 |
| docs_web_server | 文档 Web 服务 | 文档查看 |
| gitee_server | Gitee 平台 | PR、Issue 操作 |

## 启动方式

所有服务器都是独立的 stdio 进程：
```bash
python -m infrastructure.mcp_servers.shell_server
# 或用 uv：
uv run python -m infrastructure.mcp_servers.shell_server
```

## 连接方式

使用 `mcp` Python SDK 的 stdio 客户端：
```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(command="python", args=["-m", "infrastructure.mcp_servers.shell_server"])
read_stream, write_stream = await stdio_client(server_params)
session = ClientSession(read_stream, write_stream)
await session.initialize()
tools = await session.list_tools()
result = await session.call_tool("run_command", {"cmd": "echo hello"})
```

## 自包含性

所有 MCP 服务器代码是自包含的，只依赖：
- `mcp` 包（FastMCP）
- Python 标准库
- 各自的领域工具（如 Playwright for browser_server）

无 openharness 内部模块依赖，可独立运行。
