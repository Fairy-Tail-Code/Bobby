from __future__ import annotations

from pathlib import Path

from config.config import MemoryConfig
from utils.paths import get_home, get_memory_dir

ENTRYPOINT_NAME = "MEMORY.md"
LOCK_FILE_NAME = ".lock"
LEGACY_PROFILE_NAME = "user_profile.md"


def resolve_memory_dir(memory_config: MemoryConfig | None = None) -> Path:
    if memory_config and memory_config.dir:
        candidate = Path(memory_config.dir).expanduser()
        if not candidate.is_absolute():
            candidate = get_home() / candidate
        return candidate
    return get_memory_dir()


def ensure_memory_dir(memory_config: MemoryConfig | None = None) -> Path:
    memory_dir = resolve_memory_dir(memory_config)
    memory_dir.mkdir(parents=True, exist_ok=True)
    index_path = memory_dir / ENTRYPOINT_NAME
    if not index_path.exists():
        index_path.write_text("# Memory Index\n\n", encoding="utf-8")
    return memory_dir


def get_memory_index_path(memory_config: MemoryConfig | None = None) -> Path:
    return ensure_memory_dir(memory_config) / ENTRYPOINT_NAME


def get_memory_lock_path(memory_config: MemoryConfig | None = None) -> Path:
    return ensure_memory_dir(memory_config) / LOCK_FILE_NAME
