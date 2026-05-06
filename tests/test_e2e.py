from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from agents.PM import create_pm
from agents.evaluator import create_evaluator
from agents.generator import create_generator
from agents.planner import create_planner
from config.config import LlmAgentConfig, LlmConfig, load_harness_config, load_llm_config, load_mcp_config
from utils.paths import ensure_dirs, get_config_dir, get_env_path, get_session_dir, get_workspace_dir
from orchestration.termination import create_termination_check


@contextmanager
def _temp_openharness_home() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-e2e"
    home_dir = temp_root / uuid.uuid4().hex
    (home_dir / "config").mkdir(parents=True, exist_ok=True)
    try:
        yield home_dir
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)


def _build_llm_config() -> LlmConfig:
    return LlmConfig(
        pm=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.7),
        planner=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.7),
        generator=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.4),
        evaluator=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.2),
    )


def _write_runtime_config(home_dir: Path) -> None:
    (home_dir / ".env").write_text(
        "PM_MODEL=test-model\n"
        "PM_BASE_URL=http://localhost/v1\n"
        "PM_API_KEY=test-key\n"
        "PLANNER_MODEL=test-model\n"
        "PLANNER_BASE_URL=http://localhost/v1\n"
        "PLANNER_API_KEY=test-key\n"
        "GENERATOR_MODEL=test-model\n"
        "GENERATOR_BASE_URL=http://localhost/v1\n"
        "GENERATOR_API_KEY=test-key\n"
        "EVALUATOR_MODEL=test-model\n"
        "EVALUATOR_BASE_URL=http://localhost/v1\n"
        "EVALUATOR_API_KEY=test-key\n",
        encoding="utf-8",
    )
    (home_dir / "config" / "mcp.yaml").write_text(
        """
mcp_servers:
  shell:
    transport: stdio
    command: python
    args: ["-m", "test.server"]
    startup_timeout: 30
base_config:
  tool_timeout: 1800
""".strip(),
        encoding="utf-8",
    )
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
    max_messages: 500
    keep_first_message: true
    max_tokens: 200000
    auto_compact_enabled: true
    max_rounds: 50
""".strip(),
        encoding="utf-8",
    )


def test_runtime_paths_and_config_loading(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        _write_runtime_config(home_dir)
        ensure_dirs()

        assert get_env_path().exists()
        assert (get_config_dir() / "mcp.yaml").exists()
        assert (get_config_dir() / "harness.yaml").exists()
        assert get_session_dir().exists()
        assert get_workspace_dir().exists()

        llm = load_llm_config()
        mcp = load_mcp_config()
        harness = load_harness_config()
        assert llm.planner.model == "test-model"
        assert len(mcp.servers) == 1
        assert harness.max_rounds == 50
        assert len(harness.dimensions) == 4


def test_agent_creation() -> None:
    llm = _build_llm_config()
    pm = create_pm(llm)
    planner = create_planner(llm)
    generator = create_generator(llm)
    evaluator = create_evaluator(llm)
    assert pm.name == "PM"
    assert planner.name == "Planner"
    assert generator.name == "Generator"
    assert evaluator.name == "Evaluator"


def test_termination_conditions() -> None:
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD", "name": "Evaluator"})
    assert check({"content": "TERMINATE", "name": "Evaluator"})
    assert not check({"content": "Needs improvement on design", "name": "Evaluator"})
    assert not check({"content": "TERMINATE", "name": "Generator"})
