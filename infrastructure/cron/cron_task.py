"""Cron task data model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CronTaskStatus(Enum):
    """Status of a cron task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CronTask:
    """A scheduled cron task that triggers an Agent execution."""
    task_id: str
    cron_expression: str
    prompt: str
    mode: str = "swarm"
    chat_id: str = "cron"
    status: CronTaskStatus = CronTaskStatus.PENDING
    created_at: str = ""
    last_run_at: str = ""
    next_run_at: str = ""
    last_result: str = ""
    last_error: str = ""
    run_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "cron_expression": self.cron_expression,
            "prompt": self.prompt,
            "mode": self.mode,
            "chat_id": self.chat_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "run_count": self.run_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CronTask":
        """Create task from dictionary."""
        task = cls(
            task_id=data["task_id"],
            cron_expression=data["cron_expression"],
            prompt=data["prompt"],
            mode=data.get("mode", "swarm"),
            chat_id=data.get("chat_id", "cron"),
            status=CronTaskStatus(data.get("status", CronTaskStatus.PENDING.value)),
            created_at=data.get("created_at", ""),
            last_run_at=data.get("last_run_at", ""),
            next_run_at=data.get("next_run_at", ""),
            last_result=data.get("last_result", ""),
            last_error=data.get("last_error", ""),
            run_count=data.get("run_count", 0),
            metadata=data.get("metadata", {}),
        )
        return task
