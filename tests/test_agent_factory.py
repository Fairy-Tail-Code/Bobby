import pytest
from config.config import LlmConfig, LlmAgentConfig
from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from agents.PM import create_pm


@pytest.fixture
def llm_config():
    return LlmConfig(
        pm=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.7),
        planner=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.7),
        generator=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.4),
        evaluator=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.2),
    )


def test_create_pm(llm_config):
    agent = create_pm(llm_config)
    assert agent.name == "PM"
    assert "PM" in agent.description


def test_create_planner(llm_config):
    agent = create_planner(llm_config)
    assert agent.name == "Planner"
    assert "Planner" in agent.description


def test_create_generator(llm_config):
    agent = create_generator(llm_config)
    assert agent.name == "Generator"
    assert "Generator" in agent.description


def test_create_evaluator(llm_config):
    agent = create_evaluator(llm_config)
    assert agent.name == "Evaluator"
    assert "Evaluator" in agent.description
