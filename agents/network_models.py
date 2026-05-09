from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class NetworkNextStep(str, Enum):
    ASK_USER = "ask_user"
    HANDOFF_PLANNER = "handoff_planner"
    HANDOFF_GENERATOR = "handoff_generator"
    HANDOFF_EVALUATOR = "handoff_evaluator"
    COMPLETE = "complete"
    TERMINATE = "terminate"


class NetworkTurn(BaseModel):
    """Structured beta-network turn emitted by every multi-agent role."""

    message: str = Field(
        description=(
            "The full message this role wants to expose to the shared transcript. "
            "For ask_user it should contain the exact question for the human. "
            "For handoffs it should contain the exact context for the next role."
        )
    )
    next_step: NetworkNextStep = Field(
        description=(
            "The next routing action for the orchestrator. "
            "Use ask_user for human clarification/approval, "
            "handoff_planner/handoff_generator/handoff_evaluator for agent delegation, "
            "complete when the Evaluator has passed the task, "
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


ROLE_DISPLAY_NAMES = {
    "pm": "PM",
    "planner": "Planner",
    "generator": "Generator",
    "evaluator": "Evaluator",
}

OWNER_ROLE_BY_AGENT = {
    "pm": "pm_owner",
    "planner": "planner_owner",
    "generator": "generator_owner",
    "evaluator": "evaluator_owner",
}

AGENT_ROLE_BY_OWNER = {value: key for key, value in OWNER_ROLE_BY_AGENT.items()}

ALLOWED_NEXT_STEPS: dict[str, set[NetworkNextStep]] = {
    "pm": {
        NetworkNextStep.ASK_USER,
        NetworkNextStep.HANDOFF_PLANNER,
        NetworkNextStep.TERMINATE,
    },
    "planner": {
        NetworkNextStep.ASK_USER,
        NetworkNextStep.HANDOFF_GENERATOR,
        NetworkNextStep.HANDOFF_EVALUATOR,
        NetworkNextStep.TERMINATE,
    },
    "generator": {
        NetworkNextStep.ASK_USER,
        NetworkNextStep.HANDOFF_PLANNER,
        NetworkNextStep.HANDOFF_EVALUATOR,
        NetworkNextStep.TERMINATE,
    },
    "evaluator": {
        NetworkNextStep.ASK_USER,
        NetworkNextStep.HANDOFF_PLANNER,
        NetworkNextStep.HANDOFF_GENERATOR,
        NetworkNextStep.COMPLETE,
        NetworkNextStep.TERMINATE,
    },
}

