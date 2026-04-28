from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from infrastructure.skills.registry import SkillRegistry


def _make_skill(root: Path, name: str, frontmatter: str, body: str = "Skill body") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\n{frontmatter}\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


@contextmanager
def _temp_skill_root() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-skill-loader"
    root = temp_root / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_load_skill_instruction() -> None:
    with _temp_skill_root() as root:
        _make_skill(root, "test-skill", "name: test-skill\ndescription: A test")

        registry = SkillRegistry(roots=[root])
        instruction = registry.load_instruction("test-skill")
        assert "Skill body" in instruction


def test_load_skill_not_found() -> None:
    with _temp_skill_root() as root:
        registry = SkillRegistry(roots=[root])
        instruction = registry.load_instruction("nonexistent-skill")
        assert instruction is None


def test_load_skill_from_multiple_roots() -> None:
    with _temp_skill_root() as root:
        root1 = root / "root1"
        root2 = root / "root2"
        root1.mkdir()
        root2.mkdir()
        _make_skill(root1, "skill-a", "name: skill-a\ndescription: A")
        _make_skill(root2, "skill-b", "name: skill-b\ndescription: B")

        registry = SkillRegistry(roots=[root1, root2])
        assert registry.load_instruction("skill-a") is not None
        assert registry.load_instruction("skill-b") is not None


def test_list_skills() -> None:
    with _temp_skill_root() as root:
        _make_skill(root, "skill-x", "name: skill-x\ndescription: X")
        _make_skill(root, "skill-y", "name: skill-y\ndescription: Y")

        registry = SkillRegistry(roots=[root])
        skills = registry.list_skills()
        assert {s.name for s in skills} == {"skill-x", "skill-y"}


def test_frontmatter_parsing() -> None:
    with _temp_skill_root() as root:
        _make_skill(
            root,
            "browser-tester",
            "name: browser-tester\ndescription: Test browsers\nsummary: Test browsers end-to-end\nmcp_servers:\n  - browser\n  - shell",
        )

        registry = SkillRegistry(roots=[root])
        skill = registry.get_skill("browser-tester")
        assert skill is not None
        assert skill.summary == "Test browsers end-to-end"
        assert skill.mcp_servers == ["browser", "shell"]


def test_summary_fallback_to_description() -> None:
    with _temp_skill_root() as root:
        _make_skill(
            root,
            "no-summary",
            "name: no-summary\ndescription: The description text",
        )

        registry = SkillRegistry(roots=[root])
        summary = registry.get_summary("no-summary")
        assert summary == "The description text"


def test_validate_alignment_ok() -> None:
    with _temp_skill_root() as root:
        _make_skill(
            root,
            "my-skill",
            "name: my-skill\ndescription: X\nmcp_servers:\n  - shell",
        )

        registry = SkillRegistry(roots=[root], connected_servers=["shell"])
        issues = registry.validate_alignment()
        assert issues == []


def test_validate_alignment_missing() -> None:
    with _temp_skill_root() as root:
        _make_skill(
            root,
            "my-skill",
            "name: my-skill\ndescription: X\nmcp_servers:\n  - browser\n  - shell",
        )

        registry = SkillRegistry(roots=[root], connected_servers=["shell"])
        issues = registry.validate_alignment()
        assert len(issues) == 1
        assert issues[0].skill_name == "my-skill"
        assert issues[0].missing_servers == ["browser"]


def test_build_summary_block() -> None:
    with _temp_skill_root() as root:
        _make_skill(
            root,
            "skill-a",
            "name: skill-a\ndescription: Full desc\nsummary: Short summary A",
        )
        _make_skill(
            root,
            "skill-b",
            "name: skill-b\ndescription: Full desc B\nsummary: Short summary B",
        )

        registry = SkillRegistry(roots=[root])
        block = registry.build_summary_block(["skill-a", "skill-b"])
        assert "skill-a" in block
        assert "Short summary A" in block
        assert "skill-b" in block
        assert "load_skill" in block


def test_build_summary_block_missing_skill() -> None:
    with _temp_skill_root() as root:
        _make_skill(root, "real-skill", "name: real-skill\ndescription: X")

        registry = SkillRegistry(roots=[root])
        block = registry.build_summary_block(["real-skill", "ghost-skill"])
        assert "real-skill" in block
        assert "not found" in block
