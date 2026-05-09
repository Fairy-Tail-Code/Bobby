from __future__ import annotations

import logging
from typing import Any

from autogen.beta.tools.final.function_tool import FunctionTool, tool as beta_tool

from config.config import MemoryConfig
from infrastructure.memory.store import load_memory_file, save_memory_file

logger = logging.getLogger(__name__)


def _create_load_memory_tool_func(
    memory_config: MemoryConfig | None = None,
):
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


def _create_save_memory_tool_func(
    memory_config: MemoryConfig | None = None,
):
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


def build_beta_memory_tools(
    memory_config: MemoryConfig | None = None,
) -> list[FunctionTool]:
    return [
        beta_tool(
            _create_load_memory_tool_func(memory_config),
            name="load_memory",
            description=(
                "Load the full markdown content of a named memory file from the persistent memory directory. "
                "Use this after spotting a relevant entry in MEMORY.md."
            ),
            schema={
                "type": "object",
                "properties": {
                    "memory_name": {
                        "type": "string",
                        "description": (
                            "Kebab-case memory name or file stem from MEMORY.md, "
                            "for example 'db-testing-policy'."
                        ),
                    },
                },
                "required": ["memory_name"],
            },
        ),
        beta_tool(
            _create_save_memory_tool_func(memory_config),
            name="save_memory",
            description=(
                "Create or update a persistent memory markdown file and refresh MEMORY.md. "
                "Use this only for durable, non-derivable knowledge."
            ),
            schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Memory name in kebab-case, using lowercase letters, digits, and hyphens only.",
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Markdown body of the memory. Include the durable fact and, "
                            "when useful, why it matters."
                        ),
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
        ),
    ]

