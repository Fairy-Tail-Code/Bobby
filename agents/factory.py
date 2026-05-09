from __future__ import annotations

import logging

from autogen import ConversableAgent
from autogen.agentchat.group import OnCondition
from autogen.agentchat.group.handoffs import Handoffs
from autogen.agentchat.group.llm_condition import StringLLMCondition
from autogen.agentchat.group.targets.transition_target import AgentTarget, TerminateTarget

from agents.single import create_single
from config.config import (
    ContextConfig,
    HarnessConfig,
    LlmConfig,
    SkillAssignmentConfig,
    load_skill_assignment_config,
)
from infrastructure.context.auto_compact import AutoCompactTransform
from infrastructure.context.snip import create_snip_transform
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import register_tools_for_agent
from infrastructure.memory.injection import inject_memory_block
from infrastructure.memory.tool import register_memory_tools
from infrastructure.skills.registry import SkillRegistry
from infrastructure.skills.tool import register_load_skill_tool
from infrastructure.skills.skill_inject import inject_skill_summaries


logger = logging.getLogger(__name__)

_skill_assignment: SkillAssignmentConfig | None = None


def _get_skill_assignment() -> SkillAssignmentConfig:
    global _skill_assignment
    if _skill_assignment is None:
        _skill_assignment = load_skill_assignment_config()
    return _skill_assignment


def _register_context_transforms(
    agent: ConversableAgent,
    context_config: ContextConfig,
) -> None:
    """Register Level 1 (Snip) and Level 4 (Auto Compact) transforms on an agent.

    Both transforms hook into AG2's ``process_all_messages_before_reply`` so
    they run automatically on every reply generation — zero orchestration code
    needed.
    """
    if not context_config.enabled:
        return

    transforms: list = []

    # Level 1: Snip Compact — message count limiter (AG2 built-in)
    snip = create_snip_transform(
        max_messages=context_config.max_messages,
        keep_first_message=context_config.keep_first_message,
    )
    transforms.append(snip)

    # Level 4: Auto Compact — LLM summarisation
    if context_config.auto_compact_enabled:
        auto_compact = AutoCompactTransform(
            agent=agent,
            max_tokens=context_config.max_tokens,
        )
        from autogen.agentchat.contrib.capabilities.transform_messages import TransformMessages
        auto_compact_wrapper = TransformMessages(transforms=[auto_compact])
        transforms.append(auto_compact_wrapper)

    # Apply all transforms to the agent
    for transform in transforms:
        transform.add_to_agent(agent)

    logger.info(
        "Registered %d context transform(s) on agent '%s'",
        len(transforms), agent.name,
    )


def create_single_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
    harness_config: HarnessConfig | None = None,
) -> ConversableAgent:
    """Create the all-in-one Assistant agent for single mode."""
    agent = create_single(llm_config)
    sa = _get_skill_assignment()
    register_tools_for_agent(agent, mcp_manager, sa.mcp_servers.get("single", []))
    if skill_registry:
        inject_skill_summaries(agent, sa.skills.get("single", []), skill_registry)
        register_load_skill_tool(agent, skill_registry, sa.skills.get("single", []))
    if harness_config and harness_config.memory.enabled:
        inject_memory_block(agent, harness_config.memory)
        register_memory_tools(agent, harness_config.memory)
    return agent


def setup_single_handoffs(agents: dict[str, ConversableAgent]) -> None:
    """Set up handoffs for single-agent mode.

    Conversational loop: Assistant <-> assistant_owner.
    - Assistant.after_work → assistant_owner (always loops back for next input)
    - assistant_owner.after_work → Assistant (user reply triggers assistant response)
    - Termination via user sending "终止" or max_rounds
    """
    assistant = agents["assistant"]
    human_target = AgentTarget(agents["assistant_owner"])

    assistant.handoffs = Handoffs()
    assistant.handoffs.add_llm_conditions([
        OnCondition(
            target=TerminateTarget(),
            condition=StringLLMCondition(
                "TERMINATE，当用户明确表示要取消、终止、不再继续任务时"),
        ),
        OnCondition(
            target=human_target,
            condition=StringLLMCondition(
                "TRANSFER TO USER，当需要向用户提问、确认需求、或审批风险操作时"),
        ),
    ]).set_after_work(human_target)

    agents["assistant_owner"].handoffs = Handoffs()
    agents["assistant_owner"].handoffs.set_after_work(AgentTarget(assistant))
