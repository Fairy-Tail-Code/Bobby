from __future__ import annotations

from autogen import ConversableAgent,UserProxyAgent

from agents.prompts.loader import load_prompt
from infrastructure.config import LlmConfig


def create_user(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Generator agent that builds full-stack applications."""
    prompt = load_prompt("user")
    return UserProxyAgent(
        name="user",
        code_execution_config={
            "work_dir": r"C:\Users\WUJIEAI\PycharmProjects\OpenHarness\ag2_coding",
            "use_docker": False,  # 先不开启docker隔离能力
        },
    )
