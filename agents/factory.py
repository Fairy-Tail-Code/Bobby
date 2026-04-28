from __future__ import annotations

import logging
from pathlib import Path

from autogen import ConversableAgent
from autogen.agentchat.group import OnCondition
from autogen.agentchat.group.handoffs import Handoffs
from autogen.agentchat.group.targets.transition_target import AgentTarget, StayTarget, TerminateTarget
from autogen.agentchat.group.llm_condition import StringLLMCondition

from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from agents.PM import create_pm
from agents.single import create_single
from agents.user import (
    create_user,
    create_email_channel_proxies,
    create_dingtalk_channel_proxies,
    create_feishu_channel_proxies,
)
from config.config import (
    ContextConfig, HarnessConfig, LlmConfig, SkillAssignmentConfig,
    DingTalkConfig, FeishuConfig, SmtpConfig, ImapConfig,
    load_skill_assignment_config,
)
from infrastructure.context.auto_compact import AutoCompactTransform
from infrastructure.context.snip import create_snip_transform
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import register_tools_for_agent
from infrastructure.skills.registry import SkillRegistry
from infrastructure.skills.tool import register_load_skill_tool
from infrastructure.skills.skill_inject import inject_skill_summaries
from infrastructure.paths import get_user_skills_dir, get_config_dir, get_system_skills_dir


logger = logging.getLogger(__name__)

# HITL modes that use per-role channel proxies (not stdin)
_CHANNEL_MODES = {"email", "dingtalk", "feishu"}

_skill_assignment: SkillAssignmentConfig | None = None


def _get_skill_assignment() -> SkillAssignmentConfig:
    global _skill_assignment
    if _skill_assignment is None:
        config_dir = get_config_dir()
        _skill_assignment = load_skill_assignment_config(config_dir)
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


def create_pm_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager | None = None,
) -> ConversableAgent:
    """Create a PM agent with basic MCP tools (workspace, shell)."""
    agent = create_pm(llm_config)
    if mcp_manager:
        register_tools_for_agent(agent, mcp_manager, _get_skill_assignment().mcp_servers.get("pm", []))
    return agent


def create_planner_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager | None = None,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create a Planner agent with analysis skills."""
    agent = create_planner(llm_config)
    sa = _get_skill_assignment()
    if mcp_manager:
        register_tools_for_agent(agent, mcp_manager, sa.mcp_servers.get("planner", []))
    if skill_registry:
        inject_skill_summaries(agent, sa.skills.get("planner", []), skill_registry)
        register_load_skill_tool(agent, skill_registry, sa.skills.get("planner", []))
    return agent


def create_generator_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create a Generator agent with MCP tools and build skills."""
    agent = create_generator(llm_config)
    sa = _get_skill_assignment()
    register_tools_for_agent(agent, mcp_manager, sa.mcp_servers.get("generator", []))
    if skill_registry:
        inject_skill_summaries(agent, sa.skills.get("generator", []), skill_registry)
        register_load_skill_tool(agent, skill_registry, sa.skills.get("generator", []))
    return agent


def create_evaluator_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create an Evaluator agent with browser/shell tools and testing skills."""
    agent = create_evaluator(llm_config)
    sa = _get_skill_assignment()
    register_tools_for_agent(agent, mcp_manager, sa.mcp_servers.get("evaluator", []))
    if skill_registry:
        inject_skill_summaries(agent, sa.skills.get("evaluator", []), skill_registry)
        register_load_skill_tool(agent, skill_registry, sa.skills.get("evaluator", []))
    return agent

def creat_user_agent(
    llm_config: LlmConfig,
):
    agent = create_user(llm_config)
    return agent


def create_single_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create the all-in-one Assistant agent for single mode."""
    agent = create_single(llm_config)
    sa = _get_skill_assignment()
    register_tools_for_agent(agent, mcp_manager, sa.mcp_servers.get("single", []))
    if skill_registry:
        inject_skill_summaries(agent, sa.skills.get("single", []), skill_registry)
        register_load_skill_tool(agent, skill_registry, sa.skills.get("single", []))
    return agent


def setup_single_handoffs(agents: dict[str, ConversableAgent], hitl_mode: str = "stdin") -> None:
    """Set up handoffs for single-agent mode.

    Conversational loop: Assistant <-> user (or assistant_owner in channel mode).
    - Assistant.after_work → user (always loops back to user for next input)
    - user.after_work → Assistant (user reply triggers assistant response)
    - Termination via user sending "终止" or max_rounds
    """
    assistant = agents["assistant"]

    if hitl_mode in _CHANNEL_MODES:
        human_target = AgentTarget(agents["assistant_owner"])
    else:
        human_target = AgentTarget(agents["user"])

    assistant.handoffs = Handoffs()
    assistant.handoffs.add_llm_conditions([
        OnCondition(
            target=human_target,
            condition=StringLLMCondition(
                "TRANSFER TO USER，当需要向用户提问、确认需求、或审批风险操作时"),
        ),
    ]).set_after_work(human_target)

    # Human returns to Assistant after replying
    if hitl_mode in _CHANNEL_MODES:
        agents["assistant_owner"].handoffs = Handoffs()
        agents["assistant_owner"].handoffs.set_after_work(AgentTarget(assistant))
    else:
        agents["user"].handoffs = Handoffs()
        agents["user"].handoffs.set_after_work(AgentTarget(assistant))
def setup_handoffs(agents: dict[str, ConversableAgent], hitl_mode: str = "stdin") -> None:
    """Set up swarm handoff conditions between agents.

    PM -> Planner (PRD 完成)
    PM -> pm_owner (需要用户补充信息)
    Planner -> Generator (需求拆解完毕)
    Planner -> Generator/Evaluator (回答问题后交回)
    Generator -> Evaluator (编码完成)
    Generator -> Planner (需求不清晰)
    Evaluator -> Generator (审核不通过)
    Evaluator -> Planner (需求不足)
    Evaluator -> TERMINATE (审核通过)

    In email mode, each AI agent hands off to its dedicated role owner.
    In stdin mode, all hand off to a single "user" proxy.
    """
    pm = agents["pm"]
    planner = agents["planner"]
    generator = agents["generator"]
    evaluator = agents["evaluator"]

    # Determine per-role human targets
    if hitl_mode in _CHANNEL_MODES:
        pm_human = AgentTarget(agents["pm_owner"])
        planner_human = AgentTarget(agents["planner_owner"])
        generator_human = AgentTarget(agents["generator_owner"])
        evaluator_human = AgentTarget(agents["evaluator_owner"])
    else:
        user = agents["user"]
        pm_human = AgentTarget(user)
        planner_human = AgentTarget(user)
        generator_human = AgentTarget(user)
        evaluator_human = AgentTarget(user)

    # PM handoffs
    pm.handoffs = Handoffs()
    pm.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(planner),
            condition=StringLLMCondition("TRANSFER TO PLANNER，当PRD已完成且经过用户确认，可以交给Planner进行技术拆解时"),
        ),
        OnCondition(
            target=pm_human,
            condition=StringLLMCondition(
                "TRANSFER TO USER，当需要向用户提问以补充需求信息、澄清模糊之处、或确认PRD草稿时"),
        ),
    ]).set_after_work(StayTarget())

    planner.handoffs = Handoffs()
    planner.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(generator),
            condition=StringLLMCondition("TRANSFER TO GENERATOR,当plan撰写完成并需要将计划交接给generator开始编程时，或者当generator提出了问题需要向generator回答时"),
        ),
        OnCondition(
            target=AgentTarget(evaluator),
            condition=StringLLMCondition("TRANSFER TO EVALUATOR,当plan撰写完成并需要将计划交接给evaluator时，用于evaluator等待generator完成后根据计划进行验证"),
        ),
        OnCondition(
            target=planner_human,
            condition=StringLLMCondition(
                "TRANSFER TO USER,当你针对某一点模糊的信息需要用户明确/补充时，这个行为需要积极触发，目前默认至少触发一次"),
        ),
    ]).set_after_work(StayTarget())

    generator.handoffs = Handoffs()
    generator.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(evaluator),
            condition=StringLLMCondition("TRANSFER TO EVALUATOR，当代码编写完成需要交给reviewer检查时"),
        ),
        OnCondition(
            target=AgentTarget(planner),
            condition=StringLLMCondition("TRANSFER TO PLANNER，当信息不足期望向planner询问更多信息时"),
        ),
        OnCondition(
            target=generator_human,
            condition=StringLLMCondition("TRANSFER TO USER，执行风险操作时征求用户意见"),
        ),
    ]).set_after_work(StayTarget())

    evaluator.handoffs = Handoffs()
    evaluator.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(generator),
            condition=StringLLMCondition("TRANSFER TO GENERATOR"),
        ),
        OnCondition(
            target=AgentTarget(planner),
            condition=StringLLMCondition("TRANSFER TO PLANNER"),
        ),
        OnCondition(
            target=evaluator_human,
            condition=StringLLMCondition("TRANSFER TO USER，执行风险操作时征求用户意见"),
        ),
    ]).set_after_work(TerminateTarget())

    # Human proxies return to their corresponding AI agent after responding
    if hitl_mode in _CHANNEL_MODES:
        agents["pm_owner"].handoffs = Handoffs()
        agents["pm_owner"].handoffs.set_after_work(AgentTarget(pm))
        for owner_key in ("planner_owner", "generator_owner", "evaluator_owner"):
            agents[owner_key].handoffs = Handoffs()
            agents[owner_key].handoffs.set_after_work(AgentTarget(planner))
    else:
        agents["user"].handoffs = Handoffs()
        agents["user"].handoffs.set_after_work(AgentTarget(pm))
def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
    harness_config: HarnessConfig | None = None,
    smtp_config: SmtpConfig | None = None,
    imap_config: ImapConfig | None = None,
    role_emails: dict[str, str] | None = None,
    dingtalk_config: DingTalkConfig | None = None,
    role_dingtalk_ids: dict[str, str] | None = None,
    feishu_config: FeishuConfig | None = None,
    role_feishu_open_ids: dict[str, str] | None = None,
    mode: str | None = None,
) -> dict[str, ConversableAgent]:
    """Create agents based on mode.

    Args:
        mode: Override harness_config.mode. Useful for runtime switching.
              If None, reads from harness_config.

    Modes:
      - ``swarm``  : multi-agent (PM, Planner, Generator, Evaluator)
      - ``single`` : one Assistant + user proxy
    """
    hitl_mode = harness_config.hitl.mode if harness_config else "stdin"
    hitl_cfg = harness_config.hitl if harness_config else None
    effective_mode = mode or (harness_config.mode if harness_config else "swarm")

    # ---- Single mode ----
    if effective_mode == "single":
        agents: dict[str, ConversableAgent] = {
            "assistant": create_single_agent(llm_config, mcp_manager, skill_registry),
        }

        # HITL proxy for single mode
        if hitl_mode == "email" and smtp_config and imap_config and role_emails:
            proxies = create_email_channel_proxies(
                smtp_config, imap_config, hitl_cfg, role_emails,
            )
            agents.update(proxies)
        elif hitl_mode == "dingtalk" and dingtalk_config and role_dingtalk_ids:
            proxies = create_dingtalk_channel_proxies(
                dingtalk_config, hitl_cfg, role_dingtalk_ids,
            )
            agents.update(proxies)
        elif hitl_mode == "feishu" and feishu_config and role_feishu_open_ids:
            proxies = create_feishu_channel_proxies(
                feishu_config, hitl_cfg, role_feishu_open_ids,
            )
            agents.update(proxies)
        else:
            agents["user"] = creat_user_agent(llm_config)

        if harness_config and harness_config.context.enabled:
            _register_context_transforms(agents["assistant"], harness_config.context)

        setup_single_handoffs(agents, hitl_mode)
        return agents

    # ---- Swarm mode (default) ----
    agents = {
        "pm": create_pm_agent(llm_config, mcp_manager),
        "planner": create_planner_agent(llm_config, mcp_manager, skill_registry),
        "generator": create_generator_agent(
            llm_config, mcp_manager, skill_registry,
        ),
        "evaluator": create_evaluator_agent(llm_config, mcp_manager, skill_registry),
    }

    # ---- HITL proxies ----
    if hitl_mode == "email" and smtp_config and imap_config and role_emails:
        proxies = create_email_channel_proxies(
            smtp_config, imap_config, hitl_cfg, role_emails,
        )
        agents.update(proxies)
        logger.info("Created %d email proxy agents", len(proxies))

    elif hitl_mode == "dingtalk" and dingtalk_config and role_dingtalk_ids:
        proxies = create_dingtalk_channel_proxies(
            dingtalk_config, hitl_cfg, role_dingtalk_ids,
        )
        agents.update(proxies)
        logger.info("Created %d DingTalk proxy agents", len(proxies))

    elif hitl_mode == "feishu" and feishu_config and role_feishu_open_ids:
        proxies = create_feishu_channel_proxies(
            feishu_config, hitl_cfg, role_feishu_open_ids,
        )
        agents.update(proxies)
        logger.info("Created %d Feishu proxy agents", len(proxies))

    else:
        agents["user"] = creat_user_agent(llm_config)

    # Register context compression transforms (Level 1 + Level 4)
    # Only for AI agents, not for email proxies
    _ai_agent_keys = {"pm", "planner", "generator", "evaluator"}
    if harness_config and harness_config.context.enabled:
        for key in _ai_agent_keys:
            _register_context_transforms(agents[key], harness_config.context)

    setup_handoffs(agents, hitl_mode)
    return agents
