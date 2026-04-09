import pytest
from pathlib import Path
from infrastructure.config import load_llm_config, load_mcp_config, load_harness_config


def test_load_llm_config(tmp_path):
    llm_yaml = tmp_path / "llm.yaml"
    llm_yaml.write_text("""
llm:
  planner:
    model: "test-model"
    base_url: "http://localhost:11434/v1"
    api_key: "test-key"
    temperature: 0.7
  generator:
    model: "test-model"
    base_url: "http://localhost:11434/v1"
    api_key: "test-key"
    temperature: 0.4
  evaluator:
    model: "test-model"
    base_url: "http://localhost:11434/v1"
    api_key: "test-key"
    temperature: 0.2
""")
    config = load_llm_config(tmp_path)
    assert config.planner.model == "test-model"
    assert config.planner.temperature == 0.7
    assert config.generator.temperature == 0.4
    assert config.evaluator.temperature == 0.2


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