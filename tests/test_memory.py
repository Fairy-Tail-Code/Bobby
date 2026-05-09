from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from config.config import LlmAgentConfig
from config.config import MemoryConfig
import infrastructure.memory.extractor as extractor_module
from infrastructure.memory.extractor import SessionMemoryExtractor
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


def test_session_memory_extractor_persists_memories_and_refreshes_index(tmp_path, monkeypatch) -> None:
    memory_config = _memory_config(tmp_path)
    llm_config = LlmAgentConfig(model="test", base_url="http://example.com", api_key="secret")

    payload = json.dumps([
        {
            "name": "user-testing-preference",
            "memory_type": "feedback",
            "description": "The user prefers targeted smoke tests before full runs.",
            "content": "# User Testing Preference\n\nRun smoke tests before broad test suites unless requested otherwise.",
        }
    ])

    async def _fake_completion(*args, **kwargs):
        return payload

    monkeypatch.setattr(extractor_module, "get_completion_text", _fake_completion)

    extractor = SessionMemoryExtractor(llm_config, memory_config)
    persisted = asyncio.run(
        extractor.persist_from_session(
            chat_history=[
                {"role": "user", "content": "以后优先跑 smoke test，再决定要不要全量测试。"},
                {"role": "assistant", "content": "收到，我会把这个当作长期反馈。"},
            ],
            session_metadata={"session_id": "sess-1", "status": "completed"},
        )
    )

    assert len(persisted) == 1
    saved = load_memory_file("user-testing-preference", memory_config)
    assert "type: feedback" in saved
    assert "smoke tests before broad test suites" in saved

    index_text = (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8")
    assert "[User Testing Preference](user-testing-preference.md)" in index_text


def test_session_memory_extractor_skips_invalid_items(tmp_path) -> None:
    memory_config = _memory_config(tmp_path)
    llm_config = LlmAgentConfig(model="test", base_url="http://example.com", api_key="secret")
    extractor = SessionMemoryExtractor(llm_config, memory_config)

    memories = extractor._parse_response(
        json.dumps(
            [
                {"name": "bad name", "memory_type": "feedback", "description": "desc", "content": "body"},
                {"name": "valid-memory", "memory_type": "project", "description": "desc", "content": "body"},
                {"name": "bad-type", "memory_type": "unknown", "description": "desc", "content": "body"},
            ]
        )
    )

    assert len(memories) == 1
    assert memories[0].name == "valid-memory"


def test_session_memory_extractor_merges_existing_memory_before_persist(tmp_path, monkeypatch) -> None:
    memory_config = _memory_config(tmp_path)
    llm_config = LlmAgentConfig(model="test", base_url="http://example.com", api_key="secret")

    save_memory_file(
        name="user-testing-preference",
        content="# User Testing Preference\n\nRun smoke tests before broad test suites.",
        memory_type="feedback",
        description="The user prefers smoke tests before broad runs.",
        memory_config=memory_config,
    )

    responses = [
        json.dumps(
            [
                {
                    "name": "user-testing-preference",
                    "memory_type": "feedback",
                    "description": "The user prefers targeted smoke tests before full runs.",
                    "content": "# User Testing Preference\n\nRun smoke tests first, and only run the full suite when smoke fails or the user asks.",
                }
            ]
        ),
        json.dumps(
            {
                "should_write": True,
                "memory_type": "feedback",
                "description": "The user prefers smoke tests first and full runs only when needed.",
                "content": "# User Testing Preference\n\nRun smoke tests first. Only run the full suite when smoke fails or the user explicitly asks for it.",
            }
        ),
    ]

    async def _fake_completion(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(extractor_module, "get_completion_text", _fake_completion)

    extractor = SessionMemoryExtractor(llm_config, memory_config)
    persisted = asyncio.run(
        extractor.persist_from_session(
            chat_history=[
                {"role": "user", "content": "以后优先跑 smoke test，只有失败或者我明确要求时才跑全量。"},
                {"role": "assistant", "content": "收到，我会更新这条长期反馈。"},
            ],
            session_metadata={"session_id": "sess-2", "status": "completed"},
        )
    )

    assert len(persisted) == 1
    saved = load_memory_file("user-testing-preference", memory_config)
    assert "type: feedback" in saved
    assert "Only run the full suite when smoke fails" in saved
    assert "description: The user prefers smoke tests first and full runs only when needed." in saved
