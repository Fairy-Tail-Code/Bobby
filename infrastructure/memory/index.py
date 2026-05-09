from __future__ import annotations

from config.config import MemoryConfig
from infrastructure.memory.paths import ensure_memory_dir, get_memory_index_path
from infrastructure.memory.store import list_memory_records

MAX_INDEX_ENTRY_CHARS = 150
DEFAULT_INDEX_TITLE = "# Memory Index"
TRUNCATION_WARNING = "> WARNING: MEMORY.md exceeds size limits. Only partial content loaded."


def _build_index_entry(title: str, file_name: str, description: str) -> str:
    line = f"- [{title}]({file_name})"
    if description:
        line += f" - {description}"
    if len(line) > MAX_INDEX_ENTRY_CHARS:
        line = line[: MAX_INDEX_ENTRY_CHARS - 3].rstrip() + "..."
    return line


def rebuild_memory_index(memory_config: MemoryConfig | None = None) -> str:
    ensure_memory_dir(memory_config)
    index_path = get_memory_index_path(memory_config)
    records = list_memory_records(memory_config)

    lines = [DEFAULT_INDEX_TITLE, ""]
    if not records:
        lines.append("- No saved memories yet.")
    else:
        for record in records:
            lines.append(
                _build_index_entry(
                    title=record.title,
                    file_name=record.path.name,
                    description=record.description,
                )
            )

    content = "\n".join(lines).rstrip() + "\n"
    index_path.write_text(content, encoding="utf-8")
    return content


def read_memory_index_for_prompt(memory_config: MemoryConfig | None = None) -> str:
    ensure_memory_dir(memory_config)
    index_path = get_memory_index_path(memory_config)
    if not index_path.exists():
        rebuild_memory_index(memory_config)

    raw_text = index_path.read_text(encoding="utf-8")
    max_lines = memory_config.max_index_lines if memory_config else 200
    max_bytes = memory_config.max_index_bytes if memory_config else 25_000

    encoded = raw_text.encode("utf-8")
    truncated = False
    if len(encoded) > max_bytes:
        encoded = encoded[:max_bytes]
        raw_text = encoded.decode("utf-8", errors="ignore")
        truncated = True

    lines = raw_text.splitlines()
    if len(lines) > max_lines:
        raw_text = "\n".join(lines[:max_lines])
        truncated = True

    if truncated:
        raw_text = raw_text.rstrip() + "\n\n" + TRUNCATION_WARNING

    if DEFAULT_INDEX_TITLE not in raw_text:
        raw_text = DEFAULT_INDEX_TITLE + "\n\n" + raw_text.lstrip()
    return raw_text.rstrip()
