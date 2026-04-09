from __future__ import annotations

from autogen import ConversableAgent

from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from infrastructure.config import LlmConfig
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import register_tools_for_agent


def create_planner_agent(llm_config: LlmConfig, mcp_manager: McpManager | None = None) -> ConversableAgent:
    """Create a Planner agent (no MCP tools needed)."""
    return create_planner(llm_config)


def create_generator_agent(llm_config: LlmConfig, mcp_manager: McpManager) -> ConversableAgent:
    """Create a Generator agent with shell, git, workspace, and browser tools."""
    agent = create_generator(llm_config)
    register_tools_for_agent(agent, mcp_manager, ["shell", "git", "workspace", "browser"])
    return agent


def create_evaluator_agent(llm_config: LlmConfig, mcp_manager: McpManager) -> ConversableAgent:
    """Create an Evaluator agent with browser and shell tools."""
    agent = create_evaluator(llm_config)
    register_tools_for_agent(agent, mcp_manager, ["browser", "shell"])
    return agent


def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
) -> dict[str, ConversableAgent]:
    """Create all three agents with their tools."""
    return {
        "planner": create_planner_agent(llm_config, mcp_manager),
        "generator": create_generator_agent(llm_config, mcp_manager),
        "evaluator": create_evaluator_agent(llm_config, mcp_manager),
    }
