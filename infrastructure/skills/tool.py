from __future__ import annotations

import logging
from typing import Any, Callable

from autogen import ConversableAgent
from autogen.tools import Tool

from infrastructure.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


def create_load_skill_tool_func(
    skill_registry: SkillRegistry,
    available_skills: list[str],
) -> Callable[..., Any]:
    """Create an async tool function that loads full skill instructions on demand.

    Only skills in `available_skills` are accessible — others return a not-found message.
    """

    async def load_skill(skill_name: str) -> str:
        if skill_name not in available_skills:
            available = ", ".join(sorted(available_skills))
            return f"Skill '{skill_name}' is not available. Available skills: {available}"
        content = skill_registry.load_instruction(skill_name)
        if content is None:
            return f"Skill '{skill_name}' not found."
        return content

    load_skill.__name__ = "load_skill"
    load_skill.__qualname__ = "load_skill"
    return load_skill


def register_load_skill_tool(
    agent: ConversableAgent,
    skill_registry: SkillRegistry,
    available_skills: list[str],
) -> None:
    """Register the load_skill tool for an agent."""
    tool_func = create_load_skill_tool_func(skill_registry, available_skills)

    ag2_tool = Tool(
        name="load_skill",
        description=(
            "Load the full instructions for a named skill. "
            "Use this when you need detailed guidance for a specific task. "
            "Returns the complete SKILL.md content."
        ),
        func_or_tool=tool_func,
        parameters_json_schema={
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to load (e.g. 'browser-tester', 'backend-delivery').",
                },
            },
            "required": ["skill_name"],
        },
    )
    ag2_tool.register_for_llm(agent)
    ag2_tool.register_for_execution(agent)
    logger.debug("Registered load_skill tool for agent '%s'", agent.name)
