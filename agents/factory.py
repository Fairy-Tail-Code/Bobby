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
from infrastructure.config import LlmConfig
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import register_tools_for_agent
from infrastructure.skills.registry import SkillRegistry
from infrastructure.skills.tool import register_load_skill_tool

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Skill assignments per agent
PLANNER_SKILLS = [
    "repo-surveyor",
    "fullstack-analyst",
    "backend-analyst",
]

GENERATOR_SKILLS = [
    "backend-delivery",
    "frontend-delivery",
    "bug-fixer",
    "git-operator",
    "docker-operator",
    "runtime-python-toolchain",
    "runtime-node-toolchain",
    "runtime-go-toolchain",
]

EVALUATOR_SKILLS = [
    "browser-tester",
    "api-tester",
    "verification-gate",
    "test-writer",
]

# MCP server assignments per agent (must cover all MCP dependencies declared in assigned skills)
PLANNER_MCP_SERVERS = ["workspace", "shell"]
GENERATOR_MCP_SERVERS = ["shell", "git", "workspace", "browser", "docker", "database"]
EVALUATOR_MCP_SERVERS = ["browser", "shell", "http_api", "workspace"]


def _inject_skill_summaries(
    agent: ConversableAgent,
    skill_names: list[str],
    skill_registry: SkillRegistry,
) -> None:
    """Inject compact skill summaries into agent system message (progressive disclosure layer 1)."""
    summary_block = skill_registry.build_summary_block(skill_names)
    if summary_block:
        original = agent.system_message
        agent.update_system_message(original + "\n\n" + summary_block)


def create_planner_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager | None = None,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create a Planner agent with analysis skills."""
    agent = create_planner(llm_config)
    if mcp_manager:
        register_tools_for_agent(agent, mcp_manager, PLANNER_MCP_SERVERS)
    if skill_registry:
        _inject_skill_summaries(agent, PLANNER_SKILLS, skill_registry)
        register_load_skill_tool(agent, skill_registry, PLANNER_SKILLS)
    return agent


def create_generator_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create a Generator agent with MCP tools and build skills."""
    agent = create_generator(llm_config)
    register_tools_for_agent(agent, mcp_manager, GENERATOR_MCP_SERVERS)
    if skill_registry:
        _inject_skill_summaries(agent, GENERATOR_SKILLS, skill_registry)
        register_load_skill_tool(agent, skill_registry, GENERATOR_SKILLS)
    return agent


def create_evaluator_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create an Evaluator agent with browser/shell tools and testing skills."""
    agent = create_evaluator(llm_config)
    register_tools_for_agent(agent, mcp_manager, EVALUATOR_MCP_SERVERS)
    if skill_registry:
        _inject_skill_summaries(agent, EVALUATOR_SKILLS, skill_registry)
        register_load_skill_tool(agent, skill_registry, EVALUATOR_SKILLS)
    return agent


def setup_handoffs(agents: dict[str, ConversableAgent]) -> None:
    """Set up swarm handoff conditions between agents.

    Planner -> Generator (需求拆解完毕)
    Planner -> Generator/Evaluator (回答问题后交回)
    Generator -> Evaluator (编码完成)
    Generator -> Planner (需求不清晰)
    Evaluator -> Generator (审核不通过)
    Evaluator -> Planner (需求不足)
    Evaluator -> TERMINATE (审核通过)
    """
    planner = agents["planner"]
    generator = agents["generator"]
    evaluator = agents["evaluator"]

    planner.handoffs = Handoffs()
    planner.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(generator),
            condition=StringLLMCondition("TRANSFER TO GENERATOR"),
        ),
        OnCondition(
            target=AgentTarget(evaluator),
            condition=StringLLMCondition("TRANSFER TO EVALUATOR"),
        ),
    ]).set_after_work(StayTarget())

    generator.handoffs = Handoffs()
    generator.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(evaluator),
            condition=StringLLMCondition("TRANSFER TO EVALUATOR"),
        ),
        OnCondition(
            target=AgentTarget(planner),
            condition=StringLLMCondition("TRANSFER TO PLANNER"),
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
    ]).set_after_work(TerminateTarget())


def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> dict[str, ConversableAgent]:
    """Create all three agents with their tools, skills, and handoffs."""
    agents = {
        "planner": create_planner_agent(llm_config, mcp_manager, skill_registry),
        "generator": create_generator_agent(llm_config, mcp_manager, skill_registry),
        "evaluator": create_evaluator_agent(llm_config, mcp_manager, skill_registry),
    }
    setup_handoffs(agents)
    return agents
