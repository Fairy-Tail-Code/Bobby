from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads skill definitions (SKILL.md or instruction.md files) from configured root directories."""

    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    def load_instruction(self, skill_name: str) -> str | None:
        """Load the SKILL.md or instruction.md for a named skill.

        Prefers SKILL.md over instruction.md if both exist.
        """
        for root in self._roots:
            skill_path = root / skill_name
            if not skill_path.exists():
                continue

            # Prefer SKILL.md over instruction.md
            skill_md = skill_path / "SKILL.md"
            instruction_md = skill_path / "instruction.md"

            if skill_md.exists():
                return skill_md.read_text(encoding="utf-8")
            elif instruction_md.exists():
                return instruction_md.read_text(encoding="utf-8")
        return None

    def list_skills(self) -> list[str]:
        """List all skill names found across all roots.

        Recognizes skills that have either SKILL.md or instruction.md.
        """
        skills: set[str] = set()
        for root in self._roots:
            if not root.exists():
                continue
            for child in root.iterdir():
                if child.is_dir() and ((child / "SKILL.md").exists() or (child / "instruction.md").exists()):
                    skills.add(child.name)
        return sorted(skills)