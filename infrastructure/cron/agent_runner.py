"""Agent execution runner for cron tasks."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from infrastructure.session.agent_session import AgentSession
from infrastructure.session.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def run_cron_task(
    session_manager: SessionManager,
    prompt: str,
    mode: str,
    chat_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Execute a cron task by creating a temporary AgentSession.

    Args:
        session_manager: The shared SessionManager instance.
        prompt: The prompt to execute.
        mode: Execution mode (single/swarm).
        chat_id: Chat ID for session (defaults to "cron").
        task_id: Task ID for tracking.

    Returns:
        Dict containing execution results.
    """
    logger.info(f"Starting cron task execution: task_id={task_id}, mode={mode}, prompt={prompt[:100]}")

    # Create a unique chat_id for this task run
    task_chat_id = f"cron_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Create a cron-specific session directly (without frontend for cron tasks)
        session = AgentSession(
            chat_id=task_chat_id,
            frontend=session_manager._frontend,
            mcp_manager=session_manager._mcp_manager,
            llm_config=session_manager._llm_config,
            harness_config=session_manager._harness_config,
            skill_registry=session_manager._skill_registry,
            session_dir=session_manager._session_dir,
            mode=mode,
            agent_pool=session_manager._agent_pool,
            channel_factory=session_manager._channel_factory,
        )
        session.set_on_complete(lambda cid: logger.info("Cron session completed: %s", cid))

        # Start the session
        session.start(prompt)

        # Wait for completion (with timeout)
        try:
            await asyncio.wait_for(session.task, timeout=3600)
        except asyncio.TimeoutError:
            logger.error(f"Cron task timed out: task_id={task_id}")
            session.terminate()
            return {
                "success": False,
                "error": "Task timed out after 3600 seconds",
                "task_id": task_id,
            }

        # Extract chat history from session
        chat_history = session.transcript

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
