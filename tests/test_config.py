import pytest
from pathlib import Path
from infrastructure.config import load_llm_config, load_mcp_config, load_harness_config


def test_load_llm_config(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
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
        "EVALUATOR_TEMPERATURE=0.2\n"
    )
    config = load_llm_config(tmp_path)
    assert config.pm.model == "test-model"
    assert config.pm.temperature == 0.7
    assert config.planner.model == "test-model"
    assert config.planner.temperature == 0.7
    assert config.generator.temperature == 0.4
    assert config.evaluator.temperature == 0.2


def test_load_llm_config_default_temperature(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
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
        "EVALUATOR_API_KEY=k\n"
    )
    config = load_llm_config(tmp_path)
    assert config.pm.temperature == 0.7
    assert config.planner.temperature == 0.7
    assert config.generator.temperature == 0.7
    assert config.evaluator.temperature == 0.7


def test_load_mcp_config(tmp_path):
    mcp_yaml = tmp_path / "mcp.yaml"
    mcp_yaml.write_text("""
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
""")
    config = load_mcp_config(tmp_path)
    assert len(config.servers) == 2
    assert config.servers[0].name == "shell"
    assert config.servers[1].command == "python"


def test_load_harness_config(tmp_path):
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text("""
harness:
  evaluation:
    max_rounds: 15
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
    frontend: "react+vite"
    backend: "fastapi"
  context:
    strategy: "compaction"
""")
    config = load_harness_config(tmp_path)
    assert config.max_rounds == 15
    assert config.score_threshold == 7
    assert len(config.dimensions) == 4
    assert config.tech_stack["frontend"] == "react+vite"
    assert config.context_strategy == "compaction"
