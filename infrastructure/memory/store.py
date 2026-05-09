from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from filelock import FileLock

from config.config import MemoryConfig
from infrastructure.memory.paths import (
    ENTRYPOINT_NAME,
    LEGACY_PROFILE_NAME,
    ensure_memory_dir,
    get_memory_lock_path,
)
from infrastructure.memory.types import MemoryDocument, MemoryRecord, MemoryType

_VALID_MEMORY_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


def _normalize_memory_name(name: str) -> str:
    normalized = (name or "").strip()
    if normalized.endswith(".md"):
        normalized = normalized[:-3]
    if not _VALID_MEMORY_NAME.fullmatch(normalized):
        raise ValueError(
            "Memory name must be kebab-case and use only lowercase letters, numbers, and hyphens."
        )
    return normalized


def _humanize_memory_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("-"))


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_frontmatter = match.group(1)
    data = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(data, dict):
        data = {}
    body = text[match.end():]
    return data, body.lstrip()


def _derive_title(name: str, body: str) -> str:
    match = _TITLE_RE.search(body)
    if match:
        return match.group(1).strip()
    return _humanize_memory_name(name)


def _normalize_description(description: str) -> str:
    normalized = " ".join((description or "").strip().split())
    return normalized[:300]


def _normalize_body(name: str, body: str) -> str:
    cleaned = body.strip()
    if not cleaned:
        title = _humanize_memory_name(name)
        return f"# {title}\n"
    if _TITLE_RE.search(cleaned):
        return cleaned + ("\n" if not cleaned.endswith("\n") else "")
    title = _humanize_memory_name(name)
    return f"# {title}\n\n{cleaned}\n"


def _format_memory_document(
    *,
    name: str,
    description: str,
    memory_type: MemoryType,
    body: str,
) -> str:
    lines = [
        "---",
        f"name: {name}",
        f"description: {description or _humanize_memory_name(name)}",
        f"type: {memory_type.value}",
        "---",
        "",
        _normalize_body(name, body).rstrip(),
        "",
    ]
    return "\n".join(lines)


def _memory_path(name: str, memory_dir: Path) -> Path:
    return memory_dir / f"{name}.md"


def load_memory_file(name: str, memory_config: MemoryConfig | None = None) -> str:
    memory_dir = ensure_memory_dir(memory_config)
    normalized = _normalize_memory_name(name)
    path = _memory_path(normalized, memory_dir)
    if not path.exists():
        raise FileNotFoundError(f"Memory '{normalized}' not found in {memory_dir}")
    return path.read_text(encoding="utf-8")


def load_memory_document(name: str, memory_config: MemoryConfig | None = None) -> MemoryDocument:
    memory_dir = ensure_memory_dir(memory_config)
    normalized = _normalize_memory_name(name)
    path = _memory_path(normalized, memory_dir)
    if not path.exists():
        raise FileNotFoundError(f"Memory '{normalized}' not found in {memory_dir}")

    record = parse_memory_record(path)
    if record is None:
        raise ValueError(f"Memory '{normalized}' is not a valid structured memory document.")

    raw_text = path.read_text(encoding="utf-8")
    _frontmatter, body = _split_frontmatter(raw_text)
    return MemoryDocument(record=record, body=body.strip(), raw_text=raw_text)


def parse_memory_record(path: Path) -> MemoryRecord | None:
    if path.name == ENTRYPOINT_NAME or not path.is_file() or path.suffix.lower() != ".md":
        return None

    if path.name == LEGACY_PROFILE_NAME:
        return MemoryRecord(
            name="user_profile",
            title="User Profile",
            description="Legacy user profile file carried over from the original Bobby memory setup.",
            memory_type=MemoryType.USER,
            path=path,
        )

    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    name = frontmatter.get("name")
    description = frontmatter.get("description")
    memory_type = frontmatter.get("type")

    if not isinstance(name, str) or not isinstance(description, str) or not isinstance(memory_type, str):
        return None

    try:
        normalized_name = _normalize_memory_name(name)
        normalized_type = MemoryType.coerce(memory_type)
    except ValueError:
        return None

    return MemoryRecord(
        name=normalized_name,
        title=_derive_title(normalized_name, body),
        description=_normalize_description(description),
        memory_type=normalized_type,
        path=path,
    )


def list_memory_records(memory_config: MemoryConfig | None = None) -> list[MemoryRecord]:
    memory_dir = ensure_memory_dir(memory_config)
    records: list[MemoryRecord] = []
    for path in sorted(memory_dir.glob("*.md")):
        record = parse_memory_record(path)
        if record is not None:
            records.append(record)
    return records


def save_memory_file(
    *,
    name: str,
    content: str,
    memory_type: str = MemoryType.PROJECT.value,
    description: str = "",
    memory_config: MemoryConfig | None = None,
) -> Path:
    memory_dir = ensure_memory_dir(memory_config)
    normalized_name = _normalize_memory_name(name)
    normalized_type = MemoryType.coerce(memory_type)

    frontmatter, body = _split_frontmatter(content or "")
    resolved_description = _normalize_description(description)
    if not resolved_description and isinstance(frontmatter.get("description"), str):
        resolved_description = _normalize_description(frontmatter["description"])

    if isinstance(frontmatter.get("type"), str) and memory_type == MemoryType.PROJECT.value:
        normalized_type = MemoryType.coerce(frontmatter["type"])

    document = _format_memory_document(
        name=normalized_name,
        description=resolved_description,
        memory_type=normalized_type,
        body=body or content,
    )

    lock = FileLock(str(get_memory_lock_path(memory_config)))
    with lock:
        path = _memory_path(normalized_name, memory_dir)
        path.write_text(document, encoding="utf-8")

        from infrastructure.memory.index import rebuild_memory_index

        rebuild_memory_index(memory_config)
        return path
