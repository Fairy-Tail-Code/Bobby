from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from config.config import (
    ConfigError,
    load_harness_config,
    load_knowledge_config,
    load_llm_config,
    load_mcp_config,
)


@contextmanager
def _temp_openharness_home() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-config"
    home_dir = temp_root / uuid.uuid4().hex
    (home_dir / "config").mkdir(parents=True, exist_ok=True)
    try:
        yield home_dir
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)


def test_load_llm_config(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / ".env").write_text(
            "PM_MODEL=test-model\n"
            "PM_BASE_URL=http://localhost:11434/v1\n"
            "PM_API_KEY=test-key\n"
            "PM_TEMPERATURE=0.7\n"
            "PLANNER_MODEL=test-model\n"
            "PLANNER_BASE_URL=http://localhost:11434/v1\n"
            "PLANNER_API_KEY=test-key\n"
            "PLANNER_TEMPERATURE=0.7\n"
            "GENERATOR_MODEL=test-model\n"
            "GENERATOR_BASE_URL=http://localhost:11434/v1\n"
            "GENERATOR_API_KEY=test-key\n"
            "GENERATOR_TEMPERATURE=0.4\n"
            "EVALUATOR_MODEL=test-model\n"
            "EVALUATOR_BASE_URL=http://localhost:11434/v1\n"
            "EVALUATOR_API_KEY=test-key\n"
            "EVALUATOR_TEMPERATURE=0.2\n",
            encoding="utf-8",
        )

        config = load_llm_config()

        assert config.pm.model == "test-model"
        assert config.pm.temperature == 0.7
        assert config.planner.model == "test-model"
        assert config.planner.temperature == 0.7
        assert config.generator.temperature == 0.4
        assert config.evaluator.temperature == 0.2


def test_load_llm_config_accepts_utf8_bom(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        bom_prefixed_env = (
            "\ufeffPM_MODEL=test-model\n"
            "PM_BASE_URL=http://localhost:11434/v1\n"
            "PM_API_KEY=test-key\n"
            "PLANNER_MODEL=test-model\n"
            "PLANNER_BASE_URL=http://localhost:11434/v1\n"
            "PLANNER_API_KEY=test-key\n"
            "GENERATOR_MODEL=test-model\n"
            "GENERATOR_BASE_URL=http://localhost:11434/v1\n"
            "GENERATOR_API_KEY=test-key\n"
            "EVALUATOR_MODEL=test-model\n"
            "EVALUATOR_BASE_URL=http://localhost:11434/v1\n"
            "EVALUATOR_API_KEY=test-key\n"
        )
        (home_dir / ".env").write_text(bom_prefixed_env, encoding="utf-8")

        config = load_llm_config()

        assert config.pm.model == "test-model"
        assert config.planner.model == "test-model"
        assert config.generator.model == "test-model"
        assert config.evaluator.model == "test-model"


def test_load_llm_config_default_temperature(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / ".env").write_text(
            "PM_MODEL=m\n"
            "PM_BASE_URL=http://x\n"
            "PM_API_KEY=k\n"
            "PLANNER_MODEL=m\n"
            "PLANNER_BASE_URL=http://x\n"
            "PLANNER_API_KEY=k\n"
            "GENERATOR_MODEL=m\n"
            "GENERATOR_BASE_URL=http://x\n"
            "GENERATOR_API_KEY=k\n"
            "EVALUATOR_MODEL=m\n"
            "EVALUATOR_BASE_URL=http://x\n"
            "EVALUATOR_API_KEY=k\n",
            encoding="utf-8",
        )

        config = load_llm_config()

        assert config.pm.temperature == 0.7
        assert config.planner.temperature == 0.7
        assert config.generator.temperature == 0.7
        assert config.evaluator.temperature == 0.7


def test_load_llm_config_reports_all_missing_required_keys(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / ".env").write_text("", encoding="utf-8")

        try:
            load_llm_config()
        except ConfigError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected ConfigError for missing LLM config.")

        assert str(home_dir / ".env") in message
        assert "PM_MODEL" in message
        assert "PLANNER_MODEL" in message
        assert "GENERATOR_MODEL" in message
        assert "EVALUATOR_MODEL" in message
        assert ".env.example" in message
        assert "harness setup" in message


def test_load_mcp_config(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / "config" / "mcp.yaml").write_text(
            """
mcp_servers:
  shell:
    transport: stdio
    command: python
    args: ["-m", "test.server"]
    startup_timeout: 30
  git:
    transport: stdio
    command: python
    args: ["-m", "test.git"]
base_config:
  tool_timeout: 1800
""".strip(),
            encoding="utf-8",
        )

        config = load_mcp_config()

        assert len(config.servers) == 2
        assert config.servers[0].name == "shell"
        assert config.servers[1].command == "python"


def test_load_harness_config(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / "config" / "harness.yaml").write_text(
            """
harness:
  mode: swarm
  evaluation:
    score_threshold: 7
    dimensions:
      - name: design_quality
        weight: high
        threshold: 7
      - name: originality
        weight: high
        threshold: 7
      - name: craftsmanship
        weight: low
        threshold: 5
      - name: functionality
        weight: low
        threshold: 5
  tech_stack:
    frontend: react+vite
    backend: fastapi
  context:
    enabled: true
    max_messages: 60
    keep_first_message: true
    max_tokens: 80000
    auto_compact_enabled: true
    max_rounds: 15
""".strip(),
            encoding="utf-8",
        )

        config = load_harness_config()

        assert config.max_rounds == 15
        assert config.score_threshold == 7
        assert len(config.dimensions) == 4
        assert config.tech_stack["frontend"] == "react+vite"
        assert config.context.enabled is True


def test_load_knowledge_config_uses_openharness_home_paths(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / ".env").write_text(
            "KNOWLEDGE_SERVER_API_KEY=test-api-key\n"
            "KNOWLEDGE_CLIENT_ID=test-client\n",
            encoding="utf-8",
        )
        (home_dir / "config" / "harness.yaml").write_text(
            """
harness:
  knowledge:
    enabled: true
    server_url: "http://localhost:8900"
    offline_enabled: true
    pull_enabled: true
""".strip(),
            encoding="utf-8",
        )

        config = load_knowledge_config()

        assert config.enabled is True
        assert config.api_key == "test-api-key"
        assert config.client_id == "test-client"
        assert config.local_store_path == str(home_dir / "knowledge_queue.db")
        assert config.collected_dir == str(home_dir / "collected")
