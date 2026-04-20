from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from infrastructure.config import LlmConfig


def create_single(llm_config: LlmConfig) -> ConversableAgent:
    """Create the single all-in-one Assistant agent."""
    prompt = load_prompt("single")
    return ConversableAgent(
        name="Assistant",
        system_message=prompt,
        description="全栈开发助手，直接与用户对话完成需求分析、技术决策、编码委派和验证。",
        llm_config=llm_config.generator.to_llm_config(),
        human_input_mode="NEVER",
    )
