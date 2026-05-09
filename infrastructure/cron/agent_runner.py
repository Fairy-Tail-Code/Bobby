"""Agent execution runner for cron tasks."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from infrastructure.session.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def run_cron_task(
    session_manager: SessionManager,
    prompt: str,
    mode: str,
    chat_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Execute a cron task by creating a temporary SwarmSession.

    Args:
        session_manager: The shared SessionManager instance.
        prompt: The prompt to execute.
        mode: Execution mode (single/swarm).
        chat_id: Chat ID for the session (defaults to "cron").
        task_id: Task ID for tracking.

    Returns:
        Dict containing execution results.
    """
    logger.info(f"Starting cron task execution: task_id={task_id}, mode={mode}, prompt={prompt[:100]}")

    # Create a unique chat_id for this task run
    task_chat_id = f"cron_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Use session_manager to create a new session
        # We'll create a temporary session and run it directly
        await session_manager._create_session(
            chat_id=task_chat_id,
            prompt=prompt,
            open_id="",
            chat_type="p2p",
        )

        # Get the newly created session
        session = session_manager._sessions.get(task_chat_id)
        if not session:
            raise ValueError(f"Failed to create session for cron task: {task_id}")

        # Wait for completion (with timeout)
        try:
            await asyncio.wait_for(session._task, timeout=3600)
        except asyncio.TimeoutError:
            logger.error(f"Cron task timed out: task_id={task_id}")
            session.terminate()
            return {
                "success": False,
                "error": "Task timed out after 3600 seconds",
                "task_id": task_id,
            }

        # Extract chat history from the session
        chat_history = session._extract_messages_from_agents()

        # Save session history
        session_dir = Path(session_manager._session_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_file = session_dir / f"cron_history_{task_id}_{timestamp}.json"

        try:
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(chat_history, f, ensure_ascii=False, indent=2)
            logger.info(f"Cron task history saved: {session_file}")
        except Exception as e:
            logger.warning(f"Failed to save cron task history: {e}")

        logger.info(f"Cron task completed: task_id={task_id}")
        return {
            "success": True,
            "task_id": task_id,
            "chat_history_length": len(chat_history),
            "session_file": str(session_file),
        }

    except Exception as e:
        logger.exception(f"Cron task failed: task_id={task_id}, error={e}")
        return {
            "success": False,
            "error": str(e),
            "task_id": task_id,
        }
