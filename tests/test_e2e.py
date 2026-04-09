"""End-to-end structural test — verifies wiring without MCP servers or LLM calls."""
import pytest
from pathlib import Path

from infrastructure.config import load_llm_config, load_mcp_config, load_harness_config
from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from orchestration.group import create_group_chat
from orchestration.termination import create_termination_check


CONFIG_DIR = Path(__file__).parent.parent / "config"


def test_config_files_exist():
    assert (CONFIG_DIR / "llm.yaml").exists()
    assert (CONFIG_DIR / "mcp.yaml").exists()
    assert (CONFIG_DIR / "harness.yaml").exists()


def test_config_loading():
    llm = load_llm_config(CONFIG_DIR)
    mcp = load_mcp_config(CONFIG_DIR)
    harness = load_harness_config(CONFIG_DIR)
    assert llm.planner.model
    assert len(mcp.servers) >= 3
    assert harness.max_rounds > 0
    assert len(harness.dimensions) == 4


def test_agent_creation():
    llm = load_llm_config(CONFIG_DIR)
    planner = create_planner(llm)
    generator = create_generator(llm)
    evaluator = create_evaluator(llm)
    assert planner.name == "Planner"
    assert generator.name == "Generator"
    assert evaluator.name == "Evaluator"


def test_group_chat_creation():
    llm = load_llm_config(CONFIG_DIR)
    harness = load_harness_config(CONFIG_DIR)
    planner = create_planner(llm)
    generator = create_generator(llm)
    evaluator = create_evaluator(llm)
    manager = create_group_chat([planner, generator, evaluator], llm, harness)
    assert manager is not None
    assert len(manager.groupchat.agents) == 3


def test_termination_conditions():
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD"})
    assert check({"content": "TERMINATE"})
    assert not check({"content": "Needs improvement on design"})
    assert not check({"content": "Building the application now"})