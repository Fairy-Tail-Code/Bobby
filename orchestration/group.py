from __future__ import annotations

from autogen import ConversableAgent
from autogen.agentchat.group.patterns import DefaultPattern
from autogen.agentchat.group.multi_agent_chat import initiate_group_chat, a_initiate_group_chat

from infrastructure.config import HarnessConfig


def run_swarm(
    initial_agent: ConversableAgent,
    agents: list[ConversableAgent],
    prompt: str,
    harness_config: HarnessConfig,
    context_variables=None,
):
    """Run a group chat with handoffs synchronously.

    Uses DefaultPattern which respects agent.handoffs for transitions.

    Returns (chat_result, context_variables, last_speaker).
    """
    pattern = DefaultPattern(
        initial_agent=initial_agent,
        agents=agents,
        context_variables=context_variables,
    )
    return initiate_group_chat(
        pattern=pattern,
        messages=prompt,
        max_rounds=harness_config.max_rounds,
    )


async def arun_swarm(
    initial_agent: ConversableAgent,
    agents: list[ConversableAgent],
    prompt: str,
    harness_config: HarnessConfig,
    context_variables=None,
):
    """Run a group chat with handoffs asynchronously.

    Uses DefaultPattern which respects agent.handoffs for transitions.

    Returns (chat_result, context_variables, last_speaker).
    """
    pattern = DefaultPattern(
        initial_agent=initial_agent,
        agents=agents,
        context_variables=context_variables,
    )
    return await a_initiate_group_chat(
        pattern=pattern,
        messages=prompt,
        max_rounds=harness_config.max_rounds,
    )
