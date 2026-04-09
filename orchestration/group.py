from __future__ import annotations

from autogen import ConversableAgent, GroupChat, GroupChatManager

from infrastructure.config import LlmConfig, HarnessConfig
from orchestration.termination import create_termination_check


def create_group_chat(
    agents: list[ConversableAgent],
    llm_config: LlmConfig,
    harness_config: HarnessConfig,
) -> GroupChatManager:
    """Create a GroupChatManager with auto speaker selection."""
    is_termination_msg = create_termination_check()

    group_chat = GroupChat(
        agents=agents,
        messages=[],
        max_round=harness_config.max_rounds,
        speaker_selection_method="auto",
        send_introductions=True,
        max_retries_for_selecting_speaker=3,
    )

    manager_llm_config = llm_config.planner.to_llm_config()

    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config=manager_llm_config,
        is_termination_msg=is_termination_msg,
    )

    return manager
