from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SingleNextStep(str, Enum):
    ASK_USER = "ask_user"
    COMPLETE = "complete"
    TERMINATE = "terminate"


class SingleTurn(BaseModel):
    """Structured beta-single turn emitted by the Assistant agent."""

    message: str = Field(
        description=(
            "The exact user-facing message the single Assistant wants to send. "
            "For ask_user it must contain the exact question for the human."
        )
    )
    next_step: SingleNextStep = Field(
        description=(
            "The next action for the single-agent orchestrator. "
            "Use ask_user when the Assistant needs human clarification or approval, "
            "complete when the current task is finished and the session can end, "
            "terminate only when the workflow should stop immediately."
        )
    )

    @field_validator("message")
    @classmethod
    def _message_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        return value
