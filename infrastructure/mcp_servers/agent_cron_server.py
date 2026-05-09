"""Agent Cron MCP server - schedule and manage Agent tasks with cron expressions."""
from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

agent_cron_server = FastMCP("openharness-agent-cron", log_level="ERROR")

# Global task scheduler instance (set by main.py)
_task_scheduler: Any = None


def set_task_scheduler(scheduler: Any) -> None:
    """Set the global task scheduler instance."""
    global _task_scheduler
    _task_scheduler = scheduler


def get_task_scheduler() -> Any:
    """Get the global task scheduler instance."""
    return _task_scheduler


@agent_cron_server.tool(
    description=(
        "Create a new scheduled task that will automatically trigger an Agent execution. "
        "Cron expressions follow the standard format with 6 fields: "
        "minute, hour, day, month, day_of_week, year (optional). "
        "Examples: '0 9 * * *' = daily at 9am, "
        "'*/30 * * * *' = every 30 minutes, "
        "'0 9 * * 1-5' = weekdays at 9am. "
        "Default mode is 'single' (one assistant agent)."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
    ),
)
async def schedule_task(
    task_id: str,
    cron_expression: str,
    prompt: str,
    mode: str = "single",
) -> str:
    """Create a new scheduled cron task.

    Args:
        task_id: Unique identifier for this task.
        cron_expression: Cron expression for scheduling (e.g., '0 9 * * *').
        prompt: The prompt that will be sent to Agent when the task runs.
        mode: Execution mode - 'single' for single agent (default), 'swarm' for multi-agent.

    Returns:
        Success message with task details or error message.
    """
    if not task_id.strip():
        raise ValueError("Tool 'schedule_task' field 'task_id' must be a non-empty string.")
    if not cron_expression.strip():
        raise ValueError("Tool 'schedule_task' field 'cron_expression' must be a non-empty string.")
    if not prompt.strip():
        raise ValueError("Tool 'schedule_task' field 'prompt' must be a non-empty string.")
    if mode not in ("single", "swarm"):
        raise ValueError("Tool 'schedule_task' field 'mode' must be 'single' or 'swarm'.")

    scheduler = get_task_scheduler()
    if not scheduler:
        return "Error: Task scheduler not initialized."

    return await scheduler.schedule_task(task_id, cron_expression, prompt, mode)


@agent_cron_server.tool(
    description=(
        "Cancel a previously scheduled task. "
        "The task will be removed from the schedule and won't run again."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
    ),
)
async def cancel_task(task_id: str) -> str:
    """Cancel a scheduled cron task.

    Args:
        task_id: The unique identifier of the task to cancel.

    Returns:
        Success message or error message.
    """
    if not task_id.strip():
        raise ValueError("Tool 'cancel_task' field 'task_id' must be a non-empty string.")

    scheduler = get_task_scheduler()
    if not scheduler:
        return "Error: Task scheduler not initialized."

    return await scheduler.cancel_task(task_id)


@agent_cron_server.tool(
    description="List all scheduled cron tasks with their status, schedules, and run history.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
async def list_tasks() -> str:
    """List all scheduled cron tasks.

    Returns:
        Formatted string with all task details.
    """
    scheduler = get_task_scheduler()
    if not scheduler:
        return "Error: Task scheduler not initialized."

    return scheduler.list_tasks()


@agent_cron_server.tool(
    description="Get detailed status of a specific scheduled task.",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
async def get_task_status(task_id: str) -> str:
    """Get detailed status of a specific task.

    Args:
        task_id: The unique identifier of the task.

    Returns:
        Formatted string with task status details.
    """
    if not task_id.strip():
        raise ValueError("Tool 'get_task_status' field 'task_id' must be a non-empty string.")

    scheduler = get_task_scheduler()
    if not scheduler:
        return "Error: Task scheduler not initialized."

    return scheduler.get_task_status(task_id)


def build_agent_cron_server() -> FastMCP:
    """Return configured agent cron MCP server instance."""
    return agent_cron_server


def main() -> None:
    """Run agent cron MCP server over stdio."""
    build_agent_cron_server().run(transport="stdio")


if __name__ == "__main__":
    main()
