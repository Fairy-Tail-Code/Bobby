from __future__ import annotations

from pathlib import Path

import yaml


def format_as_memory_md(frontmatter: dict, content: str) -> str:
    """Format an experience as a memory markdown file with YAML frontmatter."""
    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()
    return f"---\n{fm_str}\n---\n\n{content}\n"


def write_pulled_experiences(
    experiences: list[dict],
    target_dir: str = ".openharness/memory/shared",
) -> int:
    """Write pulled experiences to local memory directory."""
    memory_dir = Path(target_dir)
    memory_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for exp in experiences:
        exp_id = exp.get("id", "unknown")[:8]
        category = exp.get("category", "general")
        filename = f"{exp_id}_{category}.md"
        filepath = memory_dir / filename

        frontmatter = {
            "name": exp.get("title", "Untitled"),
            "type": "shared_experience",
            "category": category,
            "tags": exp.get("tags", []),
            "source_client": exp.get("source_client_id", ""),
        }
        content = format_as_memory_md(frontmatter, exp.get("content", ""))
        filepath.write_text(content, encoding="utf-8")
        count += 1

    return count


def update_memory_index(memory_dir: Path) -> None:
    """Update MEMORY.md index to include shared experiences."""
    index_path = memory_dir.parent / "MEMORY.md"
    shared_dir = memory_dir / "shared"

    if not shared_dir.exists():
        return

    shared_files = sorted(shared_dir.glob("*.md"))
    if not shared_files:
        return

    lines = ["# Memory Index\n"]
    lines.append("## Shared Experiences\n")
    for f in shared_files:
        # Read first line after frontmatter as title
        title = f.stem.replace("_", " ").title()
        lines.append(f"- [{title}](shared/{f.name})\n")

    existing = ""
    if index_path.exists():
        existing = index_path.read_text(encoding="utf-8")
        # Remove old shared section if exists
        if "## Shared Experiences" in existing:
            existing = existing[: existing.index("## Shared Experiences")]

    index_path.write_text(existing + "\n".join(lines), encoding="utf-8")
