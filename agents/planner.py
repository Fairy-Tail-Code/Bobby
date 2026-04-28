from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from config.config import LlmConfig


def create_planner(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Planner agent that expands user prompts into product specs."""
    prompt = load_prompt("planner")
    return ConversableAgent(
        name="Planner",
        system_message=prompt,
        description=(
            "Planner: Receives PRD from PM and produces technical specifications. "
            "Breaks down PRD into feature lists, technical architecture, and task assignments. "
            "Does NOT implement code or collect user requirements."
        ),
        llm_config=llm_config.planner.to_llm_config(),
        human_input_mode="NEVER",
    )
