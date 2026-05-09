from __future__ import annotations

from typing import Protocol, runtime_checkable

from config.config import HarnessConfig, LlmConfig
from fronted.frontend import Frontend
from infrastructure.agent_pool import AgentPool
from infrastructure.channel.channel import ChannelAdapter
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from orchestration.network_runtime import NetworkSwarmRuntime
from orchestration.run_result import OrchestrationRunResult
from orchestration.single_runtime import SingleAgentRuntime


@runtime_checkable
class SessionRuntime(Protocol):
    async def run(
        self,
        *,
        prompt: str,
        resume_messages: list[dict] | None = None,
    ) -> OrchestrationRunResult: ...

    def get_transcript(self) -> list[dict]: ...


def create_session_runtime(
    *,
    mode: str,
    chat_id: str,
    frontend: Frontend,
    channel: ChannelAdapter | None,
    llm_config: LlmConfig,
    harness_config: HarnessConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None,
    agent_pool: AgentPool | None,
) -> SessionRuntime:
    if mode == "single":
        return SingleAgentRuntime(
            chat_id=chat_id,
            frontend=frontend,
            channel=channel,
            llm_config=llm_config,
            harness_config=harness_config,
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            agent_pool=agent_pool,
        )

    from agents.beta_factory import create_swarm_network_agents

    return NetworkSwarmRuntime(
        agents=create_swarm_network_agents(
            llm_config,
            mcp_manager,
            skill_registry,
            harness_config,
        ),
        frontend=frontend,
        channel=channel,
        chat_id=chat_id,
        max_rounds=harness_config.max_rounds,
        hitl_timeout=harness_config.hitl.timeout,
    )
