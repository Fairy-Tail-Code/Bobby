"""Handoff MCP Server - Provides tool-call-based agent handoff (mirrors AG2 mechanism).

In AG2, handoffs work by auto-generating `transfer_to_{AgentName}` tool functions.
The LLM MUST call these tools to trigger a transition — plain text doesn't work.

This MCP server replicates that: Claude Code sees `transfer_to_xxx` as real tools,
calls them when it wants to hand off, and the orchestrator reads the result.

State file (.handoff_state.json) serves as IPC between CC and orchestrator.
"""
from mcp.server.fastmcp import FastMCP
import json
from pathlib import Path

mcp = FastMCP("handoff")

STATE_FILE = Path(__file__).parent / ".handoff_state.json"


def _write(target: str):
    STATE_FILE.write_text(json.dumps({"next": target}))


@mcp.tool()
def transfer_to_planner(reason: str = "") -> str:
    """Transfer control to the planner agent for task analysis and planning."""
    _write("planner")
    return f"Handoff to planner. {reason}" if reason else "Handoff to planner."


@mcp.tool()
def transfer_to_coder(reason: str = "") -> str:
    """Transfer control to the coder agent for implementation."""
    _write("coder")
    return f"Handoff to coder. {reason}" if reason else "Handoff to coder."


@mcp.tool()
def transfer_to_reviewer(reason: str = "") -> str:
    """Transfer control to the reviewer agent for code review."""
    _write("reviewer")
    return f"Handoff to reviewer. {reason}" if reason else "Handoff to reviewer."


@mcp.tool()
def task_complete(summary: str = "") -> str:
    """Mark the task as complete. No further agent action needed."""
    _write("DONE")
    return f"Task complete. {summary}" if summary else "Task complete."


if __name__ == "__main__":
    mcp.run()
