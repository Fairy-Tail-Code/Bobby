from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads skill definitions (instruction.md files) from configured root directories."""

    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    def load_instruction(self, skill_name: str) -> str | None:
        """Load the instruction.md for a named skill."""
        for root in self._roots:
            instruction_path = root / skill_name / "instruction.md"
            if instruction_path.exists():
                return instruction_path.read_text(encoding="utf-8")
        return None

    def list_skills(self) -> list[str]:
        """List all skill names found across all roots."""
        skills: set[str] = set()
        for root in self._roots:
            if not root.exists():
                continue
            for child in root.iterdir():
                if child.is_dir() and (child / "instruction.md").exists():
                    skills.add(child.name)
        return sorted(skills)