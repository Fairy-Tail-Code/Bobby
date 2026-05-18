from __future__ import annotations

from agents.beta_factory import create_swarm_network_agents
from config.config import HarnessConfig, LlmAgentConfig, LlmConfig


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

    assert agents["pm"]._response_schema is None
    prompt_text = "\n".join(agents["pm"]._system_prompt)
    assert "正确示例" in prompt_text
    assert "不要输出 `[PM]`" in prompt_text


def test_swarm_network_agents_keep_response_schema_for_openai_compatible_backends() -> None:
    agents = create_swarm_network_agents(
        _llm_config("https://api.openai.com/v1"),
        mcp_manager=None,
        skill_registry=None,
        harness_config=HarnessConfig(),
    )

    assert agents["pm"]._response_schema is not None
