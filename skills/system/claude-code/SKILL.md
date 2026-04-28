---
name: claude-code
description: Delegate coding tasks to Claude Code via the claude_code MCP server. Use for writing code, fixing bugs, refactoring, and any implementation work that should be handled by a dedicated coding subprocess.
summary: "Delegate coding tasks to Claude Code via claude -p for implementation, bugfixes, and refactoring."
mcp_servers:
  - claude_code
  - workspace
---

# Claude Code Delegation

Use the `claude_code` MCP server to delegate coding tasks to Claude Code (`claude -p`). This replaces acpx and avoids its rate-limiting issues.

## When to use

Use this skill when you need another AI to perform coding work — writing files, fixing bugs, refactoring, running code analysis — that you cannot or should not do yourself.

## Available tools

### `claude_prompt`

One-shot prompt execution. Returns the full Claude Code output.

**Parameters:**
- `prompt` (required): The coding task description.
- `cwd`: Working directory for Claude Code. Defaults to the server's cwd.
- `model`: Claude model to use (e.g., `sonnet`, `opus`). Defaults to Claude Code's default.
- `timeout_ms`: Execution timeout in milliseconds. Default 600000 (10 min). Increase for large tasks.
- `allowed_tools`: List of tool names Claude Code is allowed to use (e.g., `["Bash", "Edit", "Read"]`).
- `disallowed_tools`: List of tool names to deny.
- `append_system_prompt`: Extra system prompt appended to Claude Code's default.

**Example usage (conceptual):**
```
claude_prompt(
  prompt="Implement a FastAPI /health endpoint in server.py",
  cwd="C:\\project",
  timeout_ms=600000,
)
```

### `claude_prompt_file`

Same as `claude_prompt` but reads the prompt from a file. Use for long, detailed prompts that would exceed shell argument limits.

**Parameters:** Same as `claude_prompt` except `prompt` is replaced by `file_path`.

**Example:**
```
claude_prompt_file(
  file_path="C:\\project\\.tasks\\task_backend.md",
  cwd="C:\\project",
  timeout_ms=3600000,
)
```

## Task delegation best practices

### Prompt structure

Each prompt should include:
1. **Goal**: What to implement or fix
2. **File paths**: Which files are involved (if known)
3. **Constraints**: Tech stack, naming conventions, what NOT to do
4. **Acceptance criteria**: How to verify the task is complete

### Prompt length

- Short tasks (< 500 words): use `claude_prompt` directly.
- Long tasks (detailed specs, multi-file instructions): write prompt to a temp file, then use `claude_prompt_file`.

### Timeout guidelines

| Task type | Recommended timeout |
|---|---|
| Small fix / single file | 300s (5 min) |
| Feature implementation | 600s (10 min) |
| Multi-file refactor | 1800s (30 min) |
| Large scaffolding | 3600s (1 hour) |

### Working directory

Always set `cwd` to the project root so Claude Code can discover CLAUDE.md and project context.

## Execution rules

- Always verify Claude Code's output before reporting completion. Use workspace tools (`read_file`, `list_files`) to inspect the result.
- If Claude Code reports an error, read the stderr output and retry with a refined prompt if appropriate.
- For multi-step work, break it into sequential calls — each with a clear, focused prompt.
- Never edit code yourself when this skill is available. Delegate all coding to Claude Code.
- Use `append_system_prompt` to inject project-specific conventions when needed.

## Return

- The Claude Code output (stdout)
- Whether execution succeeded (`ok` field)
- Any error output (stderr)
- Verification notes after inspecting the result with workspace tools
