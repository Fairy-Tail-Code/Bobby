from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from infrastructure.config import LlmConfig


def create_evaluator(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Evaluator agent that reviews applications with Playwright."""
    prompt = load_prompt("evaluator")
    return ConversableAgent(
        name="Evaluator",
        system_message=prompt,
        description=(
            "Evaluator: Strict quality reviewer for web applications. "
            "Speaks AFTER the Generator signals the application is ready. "
            "Uses browser tools to interact with running applications and evaluate design quality, "
            "originality, craftsmanship, and functionality on a 1-10 scale. "
            "Provides specific, actionable feedback with scores."
        ),
        llm_config=llm_config.evaluator.to_llm_config(),
        human_input_mode="NEVER",
    )
