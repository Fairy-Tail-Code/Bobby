from __future__ import annotations

import logging
from pathlib import Path

from autogen import ConversableAgent
from autogen.agentchat.contrib.swarm_agent import AfterWork, AfterWorkOption
from autogen.agentchat.group import OnCondition
from autogen.agentchat.group.handoffs import Handoffs
from autogen.agentchat.group.targets.transition_target import AgentTarget, TerminateTarget
from autogen.agentchat.group.llm_condition import StringLLMCondition

from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from infrastructure.config import LlmConfig
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import register_tools_for_agent
from infrastructure.skills.loader import SkillLoader

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

# MCP server assignments per agent
GENERATOR_MCP_SERVERS = ["shell", "git", "workspace", "browser", "docker", "database"]
EVALUATOR_MCP_SERVERS = ["browser", "shell", "http_api"]


def _load_skills_text(skill_names: list[str], loader: SkillLoader) -> str:
    """Load and concatenate skill instructions."""
    parts = []
    for name in skill_names:
        text = loader.load_instruction(name)
        if text:
            parts.append(f"\n--- Skill: {name} ---\n{text}")
        else:
            logger.warning("Skill '%s' not found", name)
    return "\n".join(parts)


def _inject_skills(agent: ConversableAgent, skill_names: list[str], loader: SkillLoader) -> None:
    """Load skills and append to agent's system message."""
    skills_text = _load_skills_text(skill_names, loader)
    if skills_text:
        original = agent.system_message
        agent.update_system_message(original + "\n\n## Loaded Skills\n" + skills_text)


def create_planner_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager | None = None,
    skill_loader: SkillLoader | None = None,
) -> ConversableAgent:
    """Create a Planner agent with analysis skills."""
    agent = create_planner(llm_config)
    if skill_loader:
        _inject_skills(agent, PLANNER_SKILLS, skill_loader)
    return agent


def create_generator_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_loader: SkillLoader | None = None,
) -> ConversableAgent:
    """Create a Generator agent with MCP tools and build skills."""
    agent = create_generator(llm_config)
    register_tools_for_agent(agent, mcp_manager, GENERATOR_MCP_SERVERS)
    if skill_loader:
        _inject_skills(agent, GENERATOR_SKILLS, skill_loader)
    return agent


def create_evaluator_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_loader: SkillLoader | None = None,
) -> ConversableAgent:
    """Create an Evaluator agent with browser/shell tools and testing skills."""
    agent = create_evaluator(llm_config)
    register_tools_for_agent(agent, mcp_manager, EVALUATOR_MCP_SERVERS)
    if skill_loader:
        _inject_skills(agent, EVALUATOR_SKILLS, skill_loader)
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
            condition=StringLLMCondition("需求文档已经拆解完毕，可以开始编码"),
        ),
        OnCondition(
            target=AgentTarget(evaluator),
            condition=StringLLMCondition("evaluator询问了需求信息，已补充完毕"),
        ),
        OnCondition(
            target=AgentTarget(generator),
            condition=StringLLMCondition("generator询问了需求信息，已补充完毕"),
        ),
    ])

    generator.handoffs = Handoffs()
    generator.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(evaluator),
            condition=StringLLMCondition("代码编写完成，需要审核"),
        ),
        OnCondition(
            target=AgentTarget(planner),
            condition=StringLLMCondition("需求文档不清晰，需要向 planner 询问更多信息"),
        ),
    ])

    evaluator.handoffs = Handoffs()
    evaluator.handoffs.add_llm_conditions([
        OnCondition(
            target=AgentTarget(generator),
            condition=StringLLMCondition("代码审核不通过，需要 generator 修改"),
        ),
        OnCondition(
            target=AgentTarget(planner),
            condition=StringLLMCondition("需求文档不足以支撑审核，需要向 planner 确认"),
        ),
    ]).set_after_work(TerminateTarget())


def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_loader: SkillLoader | None = None,
) -> dict[str, ConversableAgent]:
    """Create all three agents with their tools, skills, and handoffs."""
    agents = {
        "planner": create_planner_agent(llm_config, mcp_manager, skill_loader),
        "generator": create_generator_agent(llm_config, mcp_manager, skill_loader),
        "evaluator": create_evaluator_agent(llm_config, mcp_manager, skill_loader),
    }
    setup_handoffs(agents)
    return agents
