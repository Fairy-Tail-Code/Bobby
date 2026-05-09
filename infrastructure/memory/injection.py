from __future__ import annotations

from autogen import ConversableAgent

from config.config import MemoryConfig
from infrastructure.memory.index import read_memory_index_for_prompt
from infrastructure.memory.paths import ensure_memory_dir

_MEMORY_TYPES = [
    "- `user`: user profile, preferences, background, and working style.",
    "- `feedback`: corrections about how the agent should behave next time.",
    "- `project`: durable project decisions, milestones, ownership, and status.",
    "- `reference`: pointers to external systems such as dashboards, docs, or tickets.",
]


def build_memory_block(memory_config: MemoryConfig | None = None) -> str:
    memory_dir = ensure_memory_dir(memory_config)
    index_text = read_memory_index_for_prompt(memory_config)
    lines = [
        "## Project Memory",
        f"You have a persistent file-based memory system at `{memory_dir}`.",
        "Only store knowledge that cannot be reliably inferred from code, files, or git history.",
        "Use `load_memory` to read a full memory file from the index and `save_memory` to create or update durable memories.",
        "Available memory types:",
        *_MEMORY_TYPES,
        "",
        index_text,
    ]
    return "\n".join(lines).strip()


def inject_memory_block(
    agent: ConversableAgent,
    memory_config: MemoryConfig | None = None,
) -> None:
    block = build_memory_block(memory_config)
    if not block:
        return
    agent.update_system_message(agent.system_message + "\n\n" + block)
