from __future__ import annotations

import logging
import re
from typing import Any, Callable

from autogen import ConversableAgent
from autogen.tools import Tool

from config.config import MemoryConfig
from infrastructure.memory.store import load_memory_file, save_memory_file

logger = logging.getLogger(__name__)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _agent_suffix(agent_name: str) -> str:
    suffix = _NON_ALNUM_RE.sub("_", agent_name.strip().lower()).strip("_")
    return suffix or "agent"


def create_load_memory_tool_func(
    memory_config: MemoryConfig | None = None,
) -> Callable[..., Any]:
    async def load_memory(memory_name: str) -> str:
        try:
            return load_memory_file(memory_name, memory_config)
        except FileNotFoundError:
            return f"Memory '{memory_name}' not found."
        except ValueError as exc:
            return str(exc)

    load_memory.__name__ = "load_memory"
    load_memory.__qualname__ = "load_memory"
    return load_memory


def create_save_memory_tool_func(
    memory_config: MemoryConfig | None = None,
) -> Callable[..., Any]:
    async def save_memory(
        name: str,
        content: str,
        memory_type: str = "project",
        description: str = "",
    ) -> str:
        try:
            path = save_memory_file(
                name=name,
                content=content,
                memory_type=memory_type,
                description=description,
                memory_config=memory_config,
            )
        except ValueError as exc:
            return str(exc)
        return f"Memory saved to {path}"

    save_memory.__name__ = "save_memory"
    save_memory.__qualname__ = "save_memory"
    return save_memory


def register_memory_tools(
    agent: ConversableAgent,
    memory_config: MemoryConfig | None = None,
) -> None:
    suffix = _agent_suffix(agent.name)
    load_tool = Tool(
        name=f"load_memory__{suffix}",
        description=(
            "Load the full markdown content of a named memory file from the persistent memory directory. "
            "Use this after spotting a relevant entry in MEMORY.md."
        ),
        func_or_tool=create_load_memory_tool_func(memory_config),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "memory_name": {
                    "type": "string",
                    "description": "Kebab-case memory name or file stem from MEMORY.md, for example 'db-testing-policy'.",
                },
            },
            "required": ["memory_name"],
        },
    )
    load_tool.register_for_llm(agent)
    load_tool.register_for_execution(agent)

    save_tool = Tool(
        name=f"save_memory__{suffix}",
        description=(
            "Create or update a persistent memory markdown file and refresh MEMORY.md. "
            "Use this only for durable, non-derivable knowledge."
        ),
        func_or_tool=create_save_memory_tool_func(memory_config),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Memory name in kebab-case, using lowercase letters, digits, and hyphens only.",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown body of the memory. Include the durable fact and, when useful, why it matters.",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["user", "feedback", "project", "reference"],
                    "description": "Memory category.",
                },
                "description": {
                    "type": "string",
                    "description": "One-line summary shown in MEMORY.md.",
                },
            },
            "required": ["name", "content"],
        },
    )
    save_tool.register_for_llm(agent)
    save_tool.register_for_execution(agent)
    logger.debug("Registered memory tools for agent '%s'", agent.name)
