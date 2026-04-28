from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from config.config import LlmConfig


def create_pm(llm_config: LlmConfig) -> ConversableAgent:
    """Create the PM agent that transforms simple user requirements into PRDs."""
    prompt = load_prompt("pm")
    return ConversableAgent(
        name="PM",
        system_message=prompt,
        description=(
            "PM: Product Manager. Receives brief user requirements, "
            "communicates with the user to clarify needs, and produces a comprehensive PRD. "
            "Speak FIRST when a new user request arrives. "
            "Does NOT handle technical architecture or implementation."
        ),
        llm_config=llm_config.pm.to_llm_config(),
        human_input_mode="NEVER",
    )
