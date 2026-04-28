from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from config.config import LlmConfig


def create_generator(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Generator agent that builds full-stack applications."""
    prompt = load_prompt("generator")
    return ConversableAgent(
        name="Generator",
        system_message=prompt,
        description=(
            "Generator: Builds full-stack web applications from specifications. "
            "Speaks AFTER the Planner produces a specification. "
            "Uses shell, git, workspace, and browser tools to create React+Vite+FastAPI applications. "
            "Iterates based on Evaluator feedback — refines when trending well, refactors when direction is wrong."
        ),
        llm_config=llm_config.generator.to_llm_config(),
        human_input_mode="NEVER",
    )
