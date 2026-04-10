import pytest
from pathlib import Path
from infrastructure.skills.registry import SkillRegistry


def _make_skill(root: Path, name: str, frontmatter: str, body: str = "Skill body") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\n{frontmatter}\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_load_skill_instruction(tmp_path):
    _make_skill(tmp_path, "test-skill", "name: test-skill\ndescription: A test")

    registry = SkillRegistry(roots=[tmp_path])
    instruction = registry.load_instruction("test-skill")
    assert "Skill body" in instruction


def test_load_skill_not_found(tmp_path):
    registry = SkillRegistry(roots=[tmp_path])
    instruction = registry.load_instruction("nonexistent-skill")
    assert instruction is None


def test_load_skill_from_multiple_roots(tmp_path):
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    _make_skill(root1, "skill-a", "name: skill-a\ndescription: A")
    _make_skill(root2, "skill-b", "name: skill-b\ndescription: B")

    registry = SkillRegistry(roots=[root1, root2])
    assert registry.load_instruction("skill-a") is not None
    assert registry.load_instruction("skill-b") is not None


def test_list_skills(tmp_path):
    _make_skill(tmp_path, "skill-x", "name: skill-x\ndescription: X")
    _make_skill(tmp_path, "skill-y", "name: skill-y\ndescription: Y")

    registry = SkillRegistry(roots=[tmp_path])
    skills = registry.list_skills()
    assert {s.name for s in skills} == {"skill-x", "skill-y"}


def test_frontmatter_parsing(tmp_path):
    _make_skill(
        tmp_path,
        "browser-tester",
        "name: browser-tester\ndescription: Test browsers\nsummary: Test browsers end-to-end\nmcp_servers:\n  - browser\n  - shell",
    )

    registry = SkillRegistry(roots=[tmp_path])
    skill = registry.get_skill("browser-tester")
    assert skill is not None
    assert skill.summary == "Test browsers end-to-end"
    assert skill.mcp_servers == ["browser", "shell"]


def test_summary_fallback_to_description(tmp_path):
    _make_skill(
        tmp_path,
        "no-summary",
        "name: no-summary\ndescription: The description text",
    )

    registry = SkillRegistry(roots=[tmp_path])
    summary = registry.get_summary("no-summary")
    assert summary == "The description text"


def test_validate_alignment_ok(tmp_path):
    _make_skill(
        tmp_path,
        "my-skill",
        "name: my-skill\ndescription: X\nmcp_servers:\n  - shell",
    )

    registry = SkillRegistry(roots=[tmp_path], connected_servers=["shell"])
    issues = registry.validate_alignment()
    assert issues == []


def test_validate_alignment_missing(tmp_path):
    _make_skill(
        tmp_path,
        "my-skill",
        "name: my-skill\ndescription: X\nmcp_servers:\n  - browser\n  - shell",
    )

    registry = SkillRegistry(roots=[tmp_path], connected_servers=["shell"])
    issues = registry.validate_alignment()
    assert len(issues) == 1
    assert issues[0].skill_name == "my-skill"
    assert issues[0].missing_servers == ["browser"]


def test_build_summary_block(tmp_path):
    _make_skill(
        tmp_path,
        "skill-a",
        "name: skill-a\ndescription: Full desc\nsummary: Short summary A",
    )
    _make_skill(
        tmp_path,
        "skill-b",
        "name: skill-b\ndescription: Full desc B\nsummary: Short summary B",
    )

    registry = SkillRegistry(roots=[tmp_path])
    block = registry.build_summary_block(["skill-a", "skill-b"])
    assert "skill-a" in block
    assert "Short summary A" in block
    assert "skill-b" in block
    assert "load_skill" in block


def test_build_summary_block_missing_skill(tmp_path):
    _make_skill(tmp_path, "real-skill", "name: real-skill\ndescription: X")

    registry = SkillRegistry(roots=[tmp_path])
    block = registry.build_summary_block(["real-skill", "ghost-skill"])
    assert "real-skill" in block
    assert "not found" in block
