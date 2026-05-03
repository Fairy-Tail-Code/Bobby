# Task: Implement CLI Frontend for AG2 OpenHarness

## Goal
Create a CLI frontend implementation (like OpenAI Codex CLI style) for the AG2 OpenHarness project. The frontend decoupling protocol is already implemented — Feishu is now a pluggable frontend. We need a second frontend: **CLI**.

## Architecture Context
The project uses a **Frontend Protocol + ChannelAdapter** abstraction:
- `Frontend` Protocol (`infrastructure/frontend.py`): outbound messages — `send_text`, `stream_token`, `on_tool_call`
- `ChannelAdapter` ABC (`infrastructure/channel/channel.py`): bidirectional HITL — `send`, `poll_reply`, `wait_reply`, `inject_reply`
- `FeishuBotService` implements Frontend, `ChannelFeishuService` implements ChannelAdapter — these are the existing Feishu implementations

## What to Build

### 1. CLI Frontend (`infrastructure/frontend_cli.py`)
Implement `Frontend` Protocol:
- `send_text(chat_id, text)`: print to terminal with rich formatting (agent name, content)
- `stream_token(chat_id, agent_name, token)`: real-time streaming output to terminal (like Codex)
- `on_tool_call(chat_id, agent_name, tool_name)`: print tool call notification

Style reference: OpenAI Codex CLI
- Colored agent names in output
- Clean formatted output
- Tool call notifications with 🔧 prefix
- Stream tokens should print inline without newlines

### 2. CLI Channel Adapter (`infrastructure/channel/channel_cli.py`)
Implement `ChannelAdapter` for terminal-based HITL:
- `send()`: print the agent's question to terminal
- `wait_reply()`: use `asyncio` + stdin to read user input (non-blocking, with timeout)
- `inject_reply()`: for CLI, not needed (wait_reply blocks on input directly), but implement as no-op
- `get_any_pending_request_id()`: return None (CLI doesn't use request IDs the same way)

### 3. CLI Entry Point
Add `harness chat` command to `cli.py` (or a new `cli_chat.py`):
```
harness chat "Build a todo app"           # Start a session with prompt
harness chat                              # Interactive REPL mode
harness chat --mode single "quick task"   # Force single mode
harness chat --mode swarm "complex task"  # Force swarm mode
```

The `harness chat` command should:
1. Load configs (same as server.py)
2. Initialize MCP, skills, agent pool
3. Create `CLIFrontend` and `CLIChannelAdapter`
4. Create `SessionManager` with `frontend=cli_frontend`, `channel_factory=lambda chat_id: CLIChannel()`, `hitl_mode="cli"`
5. For prompt mode: call `session_manager.handle_message("cli", "user", "p2p", prompt)`
6. For REPL mode: loop reading stdin, call `handle_message` for each input
7. Handle Ctrl+C gracefully (terminate session)

### 4. Important Design Decisions

**chat_id**: Use a fixed string like `"cli"` since CLI is single-user.

**HITL in CLI**: When an agent needs human input:
- Print the question to terminal
- Show a prompt like `[agent_name is asking]: `
- User types response
- Response goes back to the agent

**Streaming**: The CLI frontend should support `stream_token` for real-time output. This means tokens print as they arrive, creating a typewriter effect.

**Colors**: Use ANSI color codes for terminal output:
- Agent names: different colors (PM=blue, Planner=green, Generator=yellow, Evaluator=magenta)
- Tool calls: cyan
- Errors: red
- User prompts: white

### 5. Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `infrastructure/frontend_cli.py` | **Create** | CLIFrontend implementing Frontend Protocol |
| `infrastructure/channel/channel_cli.py` | **Create** | CLIChannel implementing ChannelAdapter |
| `cli.py` | **Modify** | Add `harness chat` command |

### 6. Reference: How Feishu Does It (server.py)

```python
# In server.py, Feishu frontend is wired like this:
bot = FeishuBotService(app_id=..., app_secret=..., on_message=session_manager.handle_message)
session_manager._frontend = bot
session_manager._channel_factory = lambda chat_id: ChannelFeishuService(bot, chat_id)
session_manager._hitl_mode = "feishu"
```

CLI should follow the same pattern:
```python
cli_frontend = CLIFrontend()
session_manager = SessionManager(
    frontend=cli_frontend,
    channel_factory=lambda chat_id: CLIChannel(),
    hitl_mode="cli",
    ...
)
```

### 7. Constraints
- Do NOT modify any existing frontend/channel infrastructure code (frontend.py, channel.py, channel_feishu_service.py, feishu_bot.py)
- Do NOT modify server.py
- Do NOT modify swarm_session.py or session_manager.py (they already work with the abstraction)
- Only ADD new files and modify cli.py to add the `chat` command
- Use `rich` library if available, otherwise plain ANSI colors
- All new code should pass `py_compile`

### 8. SessionManager constructor signature (for reference)
```python
SessionManager(
    frontend: Frontend | None,
    mcp_manager: McpManager,
    llm_config: LlmConfig,
    harness_config: HarnessConfig,
    skill_registry: SkillRegistry | None = None,
    session_dir: str = "",
    restart_event: asyncio.Event | None = None,
    agent_pool: AgentPool | None = None,
    channel_factory: Callable[[str], ChannelAdapter] | None = None,
    hitl_mode: str = "feishu",
)
```

Note: `handle_message(self, chat_id, open_id, chat_type, text)` is the async method to call with user input.

For CLI mode, `chat_id="cli"`, `open_id="user"`, `chat_type="p2p"`.
