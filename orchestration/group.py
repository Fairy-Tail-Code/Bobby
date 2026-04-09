from __future__ import annotations

from autogen import ConversableAgent, ContextVariables
from autogen.agentchat.contrib.swarm_agent import initiate_swarm_chat, a_initiate_swarm_chat

from infrastructure.config import LlmConfig, HarnessConfig


def run_swarm(
    initial_agent: ConversableAgent,
    agents: list[ConversableAgent],
    prompt: str,
    harness_config: HarnessConfig,
    context_variables: ContextVariables | None = None,
):
    """Run a swarm chat synchronously.

    Returns (chat_result, context_variables, last_speaker).
    """
    return initiate_swarm_chat(
        initial_agent=initial_agent,
        messages=prompt,
        agents=agents,
        max_rounds=harness_config.max_rounds,
        context_variables=context_variables or ContextVariables(),
    )


async def arun_swarm(
    initial_agent: ConversableAgent,
    agents: list[ConversableAgent],
    prompt: str,
    harness_config: HarnessConfig,
    context_variables: ContextVariables | None = None,
):
    """Run a swarm chat asynchronously.

    Returns (chat_result, context_variables, last_speaker).
    """
    return await a_initiate_swarm_chat(
        initial_agent=initial_agent,
        messages=prompt,
        agents=agents,
        max_rounds=harness_config.max_rounds,
        context_variables=context_variables or ContextVariables(),
    )
