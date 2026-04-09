from __future__ import annotations

import logging
from pathlib import Path

from autogen import ConversableAgent

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


def create_planner_agent(
    llm_config: LlmConfig,
    mcp_manager: McpManager | None = None,
    skill_loader: SkillLoader | None = None,
) -> ConversableAgent:
    """Create a Planner agent with analysis skills."""
    agent = create_planner(llm_config)
    if skill_loader:
        skills_text = _load_skills_text(PLANNER_SKILLS, skill_loader)
        if skills_text:
            original = agent.system_message
            agent.update_system_message(original + "\n\n## Loaded Skills\n" + skills_text)
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
        skills_text = _load_skills_text(GENERATOR_SKILLS, skill_loader)
        if skills_text:
            original = agent.system_message
            agent.update_system_message(original + "\n\n## Loaded Skills\n" + skills_text)
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
        skills_text = _load_skills_text(EVALUATOR_SKILLS, skill_loader)
        if skills_text:
            original = agent.system_message
            agent.update_system_message(original + "\n\n## Loaded Skills\n" + skills_text)
    return agent


def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_loader: SkillLoader | None = None,
) -> dict[str, ConversableAgent]:
    """Create all three agents with their tools and skills."""
    return {
        "planner": create_planner_agent(llm_config, mcp_manager, skill_loader),
        "generator": create_generator_agent(llm_config, mcp_manager, skill_loader),
        "evaluator": create_evaluator_agent(llm_config, mcp_manager, skill_loader),
    }
