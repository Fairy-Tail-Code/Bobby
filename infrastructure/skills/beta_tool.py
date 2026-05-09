from __future__ import annotations

from autogen.beta.tools.final.function_tool import FunctionTool, tool as beta_tool

from infrastructure.skills.registry import SkillRegistry


def _create_load_skill_tool_func(
    skill_registry: SkillRegistry,
    available_skills: list[str],
):
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


def build_beta_skill_tools(
    skill_registry: SkillRegistry,
    available_skills: list[str],
) -> list[FunctionTool]:
    if not available_skills:
        return []
    return [
        beta_tool(
            _create_load_skill_tool_func(skill_registry, available_skills),
            name="load_skill",
            description=(
                "Load the full instructions for a named skill. "
                "Use this when you need detailed guidance for a specific task. "
                "Returns the complete SKILL.md content."
            ),
            schema={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": (
                            "Name of the skill to load "
                            "(e.g. 'browser-tester', 'backend-delivery')."
                        ),
                    },
                },
                "required": ["skill_name"],
            },
        )
    ]

