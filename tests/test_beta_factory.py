from __future__ import annotations

from autogen.beta import PromptedSchema

from agents.beta_factory import create_swarm_network_agents
from config.config import HarnessConfig, LlmAgentConfig, LlmConfig
from infrastructure.llm.deepseek_beta_config import DeepSeekOpenAIConfig


def _llm_config(base_url: str) -> LlmConfig:
    cfg = LlmAgentConfig(
        model="test-model",
        base_url=base_url,
        api_key="test-key",
        temperature=0.7,
    )
    return LlmConfig(
        pm=cfg,
        planner=cfg,
        generator=cfg,
        evaluator=cfg,
    )


def test_swarm_network_agents_disable_response_schema_for_deepseek() -> None:
    agents = create_swarm_network_agents(
        _llm_config("https://api.deepseek.com"),
        mcp_manager=None,
        skill_registry=None,
        harness_config=HarnessConfig(),
    )

    assert isinstance(agents["pm"].config, DeepSeekOpenAIConfig)
    assert isinstance(agents["pm"]._response_schema, PromptedSchema)
    prompt_text = "\n".join(agents["pm"]._system_prompt)
    assert "不要输出 `[PM]`" in prompt_text
    client = agents["pm"].config.create()
    assert client._create_options["extra_body"] == {
        "thinking": {
            "type": "disabled",
        }
    }


def test_swarm_network_agents_keep_response_schema_for_openai_compatible_backends() -> None:
    agents = create_swarm_network_agents(
        _llm_config("https://api.openai.com/v1"),
        mcp_manager=None,
        skill_registry=None,
        harness_config=HarnessConfig(),
    )

    assert agents["pm"]._response_schema is not None
