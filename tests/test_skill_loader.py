import pytest
from pathlib import Path
from infrastructure.skills.loader import SkillLoader


def test_load_skill_instruction(tmp_path):
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "instruction.md").write_text("# Test Skill\nDo the thing.")

    loader = SkillLoader(roots=[tmp_path])
    instruction = loader.load_instruction("test-skill")
    assert instruction == "# Test Skill\nDo the thing."


def test_load_skill_not_found(tmp_path):
    loader = SkillLoader(roots=[tmp_path])
    instruction = loader.load_instruction("nonexistent-skill")
    assert instruction is None


def test_load_skill_from_multiple_roots(tmp_path):
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    (root1 / "skill-a").mkdir()
    (root1 / "skill-a" / "instruction.md").write_text("Skill A from root1")
    (root2 / "skill-b").mkdir()
    (root2 / "skill-b" / "instruction.md").write_text("Skill B from root2")

    loader = SkillLoader(roots=[root1, root2])
    assert loader.load_instruction("skill-a") == "Skill A from root1"
    assert loader.load_instruction("skill-b") == "Skill B from root2"


def test_list_skills(tmp_path):
    (tmp_path / "skill-x").mkdir()
    (tmp_path / "skill-x" / "instruction.md").write_text("X")
    (tmp_path / "skill-y").mkdir()
    (tmp_path / "skill-y" / "instruction.md").write_text("Y")

    loader = SkillLoader(roots=[tmp_path])
    skills = loader.list_skills()
    assert set(skills) == {"skill-x", "skill-y"}