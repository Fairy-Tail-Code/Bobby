from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from infrastructure.config import LlmConfig


def create_planner(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Planner agent that expands user prompts into product specs."""
    prompt = load_prompt("planner")
    return ConversableAgent(
        name="Planner",
        system_message=prompt,
        description=(
            "Planner: Expands user requirements into detailed product specifications. "
            "Speak FIRST when a new user request arrives. "
            "Produces feature lists, technical architecture, and visual design direction. "
            "Does NOT implement code."
        ),
        llm_config=llm_config.planner.to_llm_config(),
        human_input_mode="NEVER",
    )
