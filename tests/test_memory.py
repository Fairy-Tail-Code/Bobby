from __future__ import annotations

from pathlib import Path

import pytest

from config.config import MemoryConfig
from infrastructure.memory.injection import build_memory_block
from infrastructure.memory.store import list_memory_records, load_memory_file, save_memory_file


def _memory_config(tmp_path: Path) -> MemoryConfig:
    return MemoryConfig(enabled=True, dir=str(tmp_path / "memory"))


def test_save_memory_file_writes_frontmatter_and_updates_index(tmp_path) -> None:
    memory_config = _memory_config(tmp_path)

    path = save_memory_file(
        name="db-testing-policy",
        content="# DB Testing Policy\n\nIntegration tests must hit a real database.",
        memory_type="feedback",
        description="Integration tests must use the real database.",
        memory_config=memory_config,
    )

    assert path.exists()
    saved = path.read_text(encoding="utf-8")
    assert "name: db-testing-policy" in saved
    assert "type: feedback" in saved
    assert "# DB Testing Policy" in saved

    index_text = (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "[DB Testing Policy](db-testing-policy.md)" in index_text
    assert "Integration tests must use the real database." in index_text


def test_load_memory_file_returns_saved_document(tmp_path) -> None:
    memory_config = _memory_config(tmp_path)
    save_memory_file(
        name="project-milestones",
        content="Important milestone notes.",
        memory_type="project",
        description="Major project milestones.",
        memory_config=memory_config,
    )

    loaded = load_memory_file("project-milestones", memory_config)

    assert "name: project-milestones" in loaded
    assert "# Project Milestones" in loaded
    assert "Important milestone notes." in loaded


def test_build_memory_block_includes_index_and_tool_guidance(tmp_path) -> None:
    memory_config = _memory_config(tmp_path)
    save_memory_file(
        name="grafana-links",
        content="# Grafana Links\n\nProduction dashboard lives in folder A.",
        memory_type="reference",
        description="Grafana dashboard references.",
        memory_config=memory_config,
    )

    block = build_memory_block(memory_config)

    assert "## Project Memory" in block
    assert "load_memory" in block
    assert "save_memory" in block
    assert "[Grafana Links](grafana-links.md)" in block


def test_list_memory_records_keeps_legacy_user_profile_visible(tmp_path) -> None:
    memory_config = _memory_config(tmp_path)
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "user_profile.md").write_text("# User Profile\n\nLegacy profile.", encoding="utf-8")

    records = list_memory_records(memory_config)

    assert len(records) == 1
    assert records[0].name == "user_profile"
    assert records[0].memory_type.value == "user"


def test_save_memory_file_rejects_invalid_names(tmp_path) -> None:
    memory_config = _memory_config(tmp_path)

    with pytest.raises(ValueError):
        save_memory_file(
            name="../bad-name",
            content="bad",
            memory_config=memory_config,
        )
