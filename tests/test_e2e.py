"""End-to-end structural test — verifies wiring without MCP servers or LLM calls."""
from pathlib import Path

from config.config import load_llm_config, load_mcp_config, load_harness_config
from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from agents.PM import create_pm
from agents.factory import setup_handoffs
from agents.user import create_user
from orchestration.termination import create_termination_check


PROJECT_DIR = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_DIR / "config"


def test_config_files_exist():
    assert (PROJECT_DIR / ".env").exists()
    assert (CONFIG_DIR / "mcp.yaml").exists()
    assert (CONFIG_DIR / "harness.yaml").exists()


def test_config_loading():
    llm = load_llm_config(PROJECT_DIR)
    mcp = load_mcp_config(CONFIG_DIR)
    harness = load_harness_config(CONFIG_DIR)
    assert llm.planner.model
    assert len(mcp.servers) >= 1
    assert harness.max_rounds > 0
    assert len(harness.dimensions) == 4


def test_agent_creation():
    llm = load_llm_config(PROJECT_DIR)
    pm = create_pm(llm)
    planner = create_planner(llm)
    generator = create_generator(llm)
    evaluator = create_evaluator(llm)
    assert pm.name == "PM"
    assert planner.name == "Planner"
    assert generator.name == "Generator"
    assert evaluator.name == "Evaluator"


def test_handoffs_setup():
    llm = load_llm_config(PROJECT_DIR)
    agents = {
        "pm": create_pm(llm),
        "planner": create_planner(llm),
        "generator": create_generator(llm),
        "evaluator": create_evaluator(llm),
        "user": create_user(llm),
    }
    setup_handoffs(agents)
    # Verify handoffs were set
    assert len(agents["pm"].handoffs.llm_conditions) > 0
    assert len(agents["planner"].handoffs.llm_conditions) > 0
    assert len(agents["generator"].handoffs.llm_conditions) > 0
    assert len(agents["evaluator"].handoffs.llm_conditions) > 0


def test_termination_conditions():
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD", "name": "Evaluator"})
    assert check({"content": "TERMINATE", "name": "Evaluator"})
    assert not check({"content": "Needs improvement on design", "name": "Evaluator"})
    assert not check({"content": "TERMINATE", "name": "Generator"})
