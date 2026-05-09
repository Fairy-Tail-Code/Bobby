"""Task scheduler for cron-based Agent execution."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from infrastructure.cron.cron_task import CronTask, CronTaskStatus
from infrastructure.cron.agent_runner import run_cron_task

logger = logging.getLogger(__name__)


class TaskScheduler:
    """Manages cron tasks and schedules Agent executions."""

    def __init__(
        self,
        session_manager: "SessionManager",
        storage_path: str = "cron_tasks.json",
    ) -> None:
        """Initialize the task scheduler.

        Args:
            session_manager: The shared SessionManager for creating Agent sessions.
            storage_path: Path to persistent task storage.
        """
        self.scheduler = AsyncIOScheduler()
        self.session_manager = session_manager
        self.storage_path = Path(storage_path)
        self.tasks: dict[str, CronTask] = {}
        self._job_map: dict[str, str] = {}  # task_id -> job_id

    async def initialize(self) -> None:
        """Load saved tasks and start the scheduler."""
        await self._load_tasks()
        self.scheduler.start()
        logger.info("TaskScheduler started with %d tasks", len(self.tasks))

    async def shutdown(self) -> None:
        """Stop the scheduler and save tasks."""
        self.scheduler.shutdown(wait=False)
        await self._save_tasks()
        logger.info("TaskScheduler shut down")

    async def schedule_task(
        self,
        task_id: str,
        cron_expr: str,
        prompt: str,
        mode: str = "swarm",
        chat_id: str = "cron",
    ) -> str:
        """Schedule a new cron task.

        Args:
            task_id: Unique task identifier.
            cron_expr: Cron expression (e.g., "0 9 * * *" for daily at 9am).
            prompt: The prompt to execute.
            mode: Execution mode (single/swarm).
            chat_id: Chat ID for the session.

        Returns:
            Success/error message.
        """
        if task_id in self.tasks:
            return f"Task '{task_id}' already exists. Use cancel_task first to replace it."

        # Validate cron expression by trying to create a trigger
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except Exception as e:
            return f"Invalid cron expression: {e}"

        # Create task
        task = CronTask(
            task_id=task_id,
            cron_expression=cron_expr,
            prompt=prompt,
            mode=mode,
            chat_id=chat_id,
            status=CronTaskStatus.PENDING,
        )

        # Add to scheduler
        job = self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            args=[task_id],
            id=f"job_{task_id}",
            name=f"cron_{task_id}",
        )

        # Update task with next run time
        task.next_run_at = job.next_run_time.isoformat() if job.next_run_time else ""

        self.tasks[task_id] = task
        self._job_map[task_id] = job.id
        await self._save_tasks()

        logger.info(
            "Task scheduled: task_id=%s, cron=%s, next_run=%s",
            task_id, cron_expr, task.next_run_at,
        )

        return (
            f"Task '{task_id}' scheduled successfully.\n"
            f"Cron: {cron_expr}\n"
            f"Next run: {task.next_run_at}"
        )

    async def cancel_task(self, task_id: str) -> str:
        """Cancel a scheduled task.

        Args:
            task_id: Task identifier to cancel.

        Returns:
            Success/error message.
        """
        if task_id not in self.tasks:
            return f"Task '{task_id}' not found."

        # Remove from scheduler
        job_id = self._job_map.get(task_id)
        if job_id:
            try:
                self.scheduler.remove_job(job_id)
            except Exception as e:
                logger.warning("Failed to remove job: %s", e)

        # Update task status
        self.tasks[task_id].status = CronTaskStatus.CANCELLED
        del self._job_map[task_id]
        await self._save_tasks()

        logger.info("Task cancelled: task_id=%s", task_id)
        return f"Task '{task_id}' has been cancelled."

    def list_tasks(self) -> str:
        """List all scheduled tasks.

        Returns:
            Formatted string listing all tasks.
        """
        if not self.tasks:
            return "No scheduled tasks."

        lines = ["Scheduled Tasks:", ""]
        for task in sorted(self.tasks.values(), key=lambda t: t.created_at):
            lines.append(f"- ID: {task.task_id}")
            lines.append(f"  Status: {task.status.value}")
            lines.append(f"  Cron: {task.cron_expression}")
            lines.append(f"  Mode: {task.mode}")
            lines.append(f"  Prompt: {task.prompt[:100]}{'...' if len(task.prompt) > 100 else ''}")
            lines.append(f"  Runs: {task.run_count}")
            if task.next_run_at:
                lines.append(f"  Next run: {task.next_run_at}")
            if task.last_run_at:
                lines.append(f"  Last run: {task.last_run_at}")
            if task.last_error:
                lines.append(f"  Last error: {task.last_error}")
            lines.append("")

        return "\n".join(lines)

    def get_task_status(self, task_id: str) -> str:
        """Get detailed status of a specific task.

        Args:
            task_id: Task identifier.

        Returns:
            Formatted string with task status.
        """
        task = self.tasks.get(task_id)
        if not task:
            return f"Task '{task_id}' not found."

        return (
            f"Task: {task.task_id}\n"
            f"Status: {task.status.value}\n"
            f"Cron: {task.cron_expression}\n"
            f"Mode: {task.mode}\n"
            f"Prompt: {task.prompt}\n"
            f"Created: {task.created_at}\n"
            f"Runs: {task.run_count}\n"
            f"Next run: {task.next_run_at or 'N/A'}\n"
            f"Last run: {task.last_run_at or 'N/A'}\n"
            f"Last result: {task.last_result or 'N/A'}\n"
            f"Last error: {task.last_error or 'None'}"
        )

    async def _execute_task(self, task_id: str) -> None:
        """Execute a scheduled task.

        Args:
            task_id: Task identifier to execute.
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning("Task not found during execution: task_id=%s", task_id)
            return

        logger.info("Executing cron task: task_id=%s", task_id)

        # Update task status
        task.status = CronTaskStatus.RUNNING
        task.last_run_at = datetime.now().isoformat()

        try:
            # Execute the task
            result = await run_cron_task(
                session_manager=self.session_manager,
                prompt=task.prompt,
                mode=task.mode,
                chat_id=task.chat_id,
                task_id=task_id,
            )

            if result.get("success"):
                task.status = CronTaskStatus.PENDING
                task.last_result = f"Completed successfully, history length: {result.get('chat_history_length', 0)}"
            else:
                task.status = CronTaskStatus.FAILED
                task.last_error = result.get("error", "Unknown error")

            # Update next run time
            job_id = self._job_map.get(task_id)
            if job_id:
                job = self.scheduler.get_job(job_id)
                if job:
                    task.next_run_at = job.next_run_time.isoformat() if job.next_run_time else ""

            task.run_count += 1
            await self._save_tasks()

        except Exception as e:
            logger.exception("Cron task execution failed: task_id=%s", task_id)
            task.status = CronTaskStatus.FAILED
            task.last_error = str(e)
            task.run_count += 1
            await self._save_tasks()

    async def _load_tasks(self) -> None:
        """Load tasks from persistent storage."""
        if not self.storage_path.exists():
            logger.info("No existing tasks file found")
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for task_data in data.get("tasks", []):
                task = CronTask.from_dict(task_data)
                # Only restore pending tasks, skip completed/failed ones
                if task.status == CronTaskStatus.PENDING:
                    self.tasks[task.task_id] = task
                    # Reschedule
                    try:
                        trigger = CronTrigger.from_crontab(task.cron_expression)
                        job = self.scheduler.add_job(
                            self._execute_task,
                            trigger=trigger,
                            args=[task.task_id],
                            id=f"job_{task.task_id}",
                            name=f"cron_{task.task_id}",
                        )
                        self._job_map[task.task_id] = job.id
                        if job.next_run_time:
                            task.next_run_at = job.next_run_time.isoformat()
                    except Exception as e:
                        logger.warning("Failed to reschedule task %s: %s", task.task_id, e)

            logger.info("Loaded %d tasks from storage", len(self.tasks))
        except Exception as e:
            logger.warning("Failed to load tasks: %s", e)

    async def _save_tasks(self) -> None:
        """Save tasks to persistent storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "tasks": [task.to_dict() for task in self.tasks.values()],
                "saved_at": datetime.now().isoformat(),
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Failed to save tasks: %s", e)
