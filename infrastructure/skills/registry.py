from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


@dataclass
class SkillMeta:
    name: str
    description: str
    summary: str
    mcp_servers: list[str]
    instruction_path: Path


@dataclass
class AlignmentIssue:
    skill_name: str
    missing_servers: list[str]
    level: str = "warning"


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Parse YAML frontmatter from a SKILL.md file without importing yaml.

    Handles simple key: value and key:\\n  - item lists.
    """
    meta: dict[str, object] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            continue  # list items handled by parent key
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value:
            meta[key] = value
        else:
            # Look ahead for list items
            meta[key] = True  # placeholder, replaced below
    return meta


def _parse_frontmatter_yaml(text: str) -> dict[str, object]:
    """Parse frontmatter using yaml if available, with text fallback."""
    match = _FRONTMATTER_RE.search(text)
    if not match:
        return {}
    frontmatter_text = match.group(1)
    try:
        import yaml
        return yaml.safe_load(frontmatter_text) or {}
    except Exception:
        return _parse_frontmatter(frontmatter_text)


def _extract_list(value: object) -> list[str]:
    """Extract a list of strings from a frontmatter value."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


@dataclass
class SkillRegistry:
    """Discovers, validates, and loads skills with MCP dependency tracking."""

    roots: list[Path]
    connected_servers: list[str] = field(default_factory=list)
    _cache: dict[str, SkillMeta] | None = field(default=None, init=False, repr=False)

    def _scan_skills(self) -> dict[str, SkillMeta]:
        """Discover all skills across root directories (cached after first call)."""
        if self._cache is not None:
            return self._cache
        skills: dict[str, SkillMeta] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for child in root.iterdir():
                skill_md = child / "SKILL.md"
                if not child.is_dir() or not skill_md.exists():
                    continue
                text = skill_md.read_text(encoding="utf-8")
                meta = _parse_frontmatter_yaml(text)
                name = meta.get("name", child.name)
                description = str(meta.get("description", ""))
                summary = str(meta.get("summary", "")) or description
                mcp_servers = _extract_list(meta.get("mcp_servers"))
                skills[name] = SkillMeta(
                    name=name,
                    description=description,
                    summary=summary,
                    mcp_servers=mcp_servers,
                    instruction_path=skill_md,
                )
        self._cache = skills
        return skills

    def list_skills(self) -> list[SkillMeta]:
        """Return metadata for all discovered skills."""
        return list(self._scan_skills().values())

    def get_skill(self, skill_name: str) -> SkillMeta | None:
        """Return metadata for one skill."""
        return self._scan_skills().get(skill_name)

    def get_summary(self, skill_name: str) -> str | None:
        """Return the summary line for a skill."""
        skill = self.get_skill(skill_name)
        return skill.summary if skill else None

    def load_instruction(self, skill_name: str) -> str | None:
        """Load the full SKILL.md content for a skill."""
        skill = self.get_skill(skill_name)
        if skill is None:
            return None
        return skill.instruction_path.read_text(encoding="utf-8")

    def validate_alignment(self) -> list[AlignmentIssue]:
        """Check that each skill's MCP dependencies are connected."""
        issues: list[AlignmentIssue] = []
        connected = set(self.connected_servers)
        for skill in self.list_skills():
            if not skill.mcp_servers:
                continue
            missing = [s for s in skill.mcp_servers if s not in connected]
            if missing:
                issues.append(AlignmentIssue(
                    skill_name=skill.name,
                    missing_servers=missing,
                ))
                logger.warning(
                    "Skill '%s' needs MCP servers %s but %s not connected",
                    skill.name,
                    skill.mcp_servers,
                    missing,
                )
        return issues

    def build_summary_block(self, skill_names: list[str]) -> str:
        """Generate a compact skill catalog for injection into agent system message."""
        all_skills = self._scan_skills()
        lines = ["## Available Skills", ""]
        lines.append("Call `load_skill(skill_name)` to get full instructions for any skill below.")
        lines.append("")
        for name in skill_names:
            skill = all_skills.get(name)
            if skill:
                lines.append(f"- **{name}**: {skill.summary}")
            else:
                lines.append(f"- **{name}**: *(skill not found)*")
        lines.append("")
        return "\n".join(lines)
