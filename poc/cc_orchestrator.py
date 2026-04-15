"""
CC Orchestrator - Multi-agent system with AG2-style tool-call handoff.

Architecture (mirrors AG2):
    ┌─────────────────────────────────────────────┐
    │  Orchestrator (this file)                    │
    │  1. invoke CC with --mcp-config + tools      │
    │  2. CC sees handoff tools (transfer_to_xxx)  │
    │  3. CC calls tool → state file written       │
    │  4. read state → route to next agent         │
    └─────────────────────────────────────────────┘

AG2 equivalent:
    AG2:  LLM calls transfer_to_Generator_1() → GroupToolExecutor → route
    Ours: CC calls transfer_to_coder (MCP)    → state file        → route

Both use TOOL CALLS, not text parsing, for handoff.

Usage:
    python poc/cc_orchestrator.py "Create a FastAPI hello world"
    python poc/cc_orchestrator.py  # interactive mode
"""

import subprocess
import json
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────

POC_DIR = Path(__file__).parent
STATE_FILE = POC_DIR / ".handoff_state.json"
MCP_CONFIG_FILE = POC_DIR / "mcp_config.json"
HANDOFF_SERVER = POC_DIR / "handoff_server.py"

MAX_CONTEXT_MESSAGES = 6


# ── Agent Definitions ──────────────────────────────────────────────
# Each agent has:
#   - system: role prompt with explicit handoff tool instructions
#   - disallowed_tools: tools this agent CANNOT use (forces collaboration)
#
# Key insight from AG2 docs: "LLM 必须调用 handoff tool function 才能触发转移，
# 不能仅输出文本。指示模型调用 handoff tool，不要写纯文本。"

AGENTS = {
    "planner": {
        "system": (
            "You are a task planner. Analyze the task and create a clear, actionable plan.\n"
            "You can ONLY read and search files — you CANNOT write or execute anything.\n\n"
            "## Handoff Rules\n"
            "You have a `transfer_to_coder` tool in your tool list.\n"
            "When your plan is ready, you MUST call `transfer_to_coder` with a brief reason.\n"
            "Do NOT write transfer phrases as plain text — call the tool."
        ),
        "disallowed_tools": "Write,Edit,Bash,NotebookEdit",
    },
    "coder": {
        "system": (
            "You are an expert programmer. You receive a plan from the planner.\n"
            "Implement it using your full toolset (Read, Write, Edit, Bash, etc.).\n\n"
            "## Handoff Rules\n"
            "You have a `transfer_to_reviewer` tool in your tool list.\n"
            "When implementation is done, you MUST call `transfer_to_reviewer`.\n"
            "Do NOT write transfer phrases as plain text — call the tool."
        ),
        # coder has full tools — no restriction
    },
    "reviewer": {
        "system": (
            "You are a code reviewer. Read the changed files and review for correctness.\n"
            "You can ONLY read files — you CANNOT modify anything.\n\n"
            "## Handoff Rules\n"
            "You have `transfer_to_coder` and `task_complete` tools.\n"
            "- If issues found: call `transfer_to_coder` with what needs fixing.\n"
            "- If everything looks good: call `task_complete` with a summary.\n"
            "Do NOT write transfer phrases as plain text — call the tool."
        ),
        "disallowed_tools": "Write,Edit,Bash,NotebookEdit",
    },
}


# ── MCP Config Generation ─────────────────────────────────────────

def _create_mcp_config():
    """Generate mcp-config.json so CC discovers the handoff tools."""
    config = {
        "mcpServers": {
            "handoff": {
                "command": sys.executable,
                "args": [str(HANDOFF_SERVER)],
            }
        }
    }
    MCP_CONFIG_FILE.write_text(json.dumps(config, indent=2))


# ── Claude Code Invocation ─────────────────────────────────────────

def invoke_cc(system_prompt: str, user_prompt: str, disallowed: str | None = None) -> str:
    """Call Claude Code CLI with MCP handoff tools available."""
    full_prompt = f"<system>\n{system_prompt}\n</system>\n\n{user_prompt}"

    cmd = f'claude -p --output-format json --mcp-config "{MCP_CONFIG_FILE}"'
    if disallowed:
        cmd += f' --disallowedTools "{disallowed}"'

    result = subprocess.run(
        cmd,
        input=full_prompt,
        capture_output=True,
        text=True,
        timeout=600,
        shell=True,
        encoding="utf-8",
    )

    if result.returncode != 0:
        return f"[ERROR] claude exited {result.returncode}: {result.stderr.strip()}"

    try:
        data = json.loads(result.stdout)
        return data.get("result", result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


# ── State File IPC ─────────────────────────────────────────────────
# The MCP handoff tools write to .handoff_state.json.
# Orchestrator reads it after CC finishes to determine routing.

def _clean_state():
    STATE_FILE.write_text("{}")


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ── Context Builder ────────────────────────────────────────────────

def _build_context(history: list[dict]) -> str:
    if not history:
        return ""
    recent = history[-MAX_CONTEXT_MESSAGES:]
    parts = [f"[{m['agent']}]:\n{m['content']}" for m in recent]
    return "Conversation so far:\n\n" + "\n\n".join(parts)


# ── Orchestrator Loop ──────────────────────────────────────────────

def run(task: str, start: str = "planner", max_rounds: int = 10):
    _create_mcp_config()
    history: list[dict] = []
    current = start

    print(f"{'=' * 60}")
    print(f"TASK: {task}")
    print(f"{'=' * 60}\n")

    for rnd in range(1, max_rounds + 1):
        agent = AGENTS[current]
        context = _build_context(history)
        user_prompt = f"Task: {task}\n\n{context}" if context else f"Task: {task}"

        # Clean state before each CC invocation
        _clean_state()

        print(f"[Round {rnd}] >>> {current}")
        print("-" * 40)

        response = invoke_cc(
            agent["system"],
            user_prompt,
            disallowed=agent.get("disallowed_tools"),
        )

        if not response:
            print("[orchestrator] empty response, stopping.")
            break

        print(response)
        print("-" * 40)

        # Record to history
        history.append({"agent": current, "content": response})

        # Read handoff state (written by MCP tool call)
        state = _read_state()
        next_agent = state.get("next")

        if next_agent == "DONE":
            print(f"\n[orchestrator] task complete in {rnd} rounds.")
            break
        elif next_agent and next_agent in AGENTS:
            print(f"[orchestrator] handoff: {current} → {next_agent}\n")
            current = next_agent
        else:
            print(f"[orchestrator] no handoff tool called, stopping. state={state}")
            break
    else:
        print(f"\n[orchestrator] max rounds ({max_rounds}) reached.")


# ── Entry Point ────────────────────────────────────────────────────

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("Task: ")
    if not task.strip():
        print("No task provided.")
        sys.exit(1)
    run(task)
