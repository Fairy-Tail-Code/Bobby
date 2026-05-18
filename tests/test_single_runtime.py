from __future__ import annotations

import asyncio

from autogen.beta import Agent, PromptedSchema
from autogen.beta.testing import TestConfig

from agents.single_models import SingleNextStep, SingleTurn
from config.config import HarnessConfig, LlmAgentConfig, LlmConfig
from orchestration.single_runtime import SingleAgentRuntime


def test_preprocess_resume_messages_strips_unknown_names() -> None:
    messages = [
        {"role": "assistant", "name": "assistant", "content": "ok"},
        {"role": "assistant", "name": "chat_manager", "content": "route"},
    ]

    result = SingleAgentRuntime.preprocess_resume_messages(messages, {"assistant", "assistant_owner"})

    assert result[0]["name"] == "assistant"
    assert "name" not in result[1]


def test_strip_terminate_from_last_message_only_touches_last_content() -> None:
    messages = [
        {"role": "assistant", "content": "keep TERMINATE inside history"},
        {"role": "assistant", "content": "done TERMINATE"},
    ]

    result = SingleAgentRuntime.strip_terminate_from_last_message(messages)

    assert result[0]["content"] == "keep TERMINATE inside history"
    assert result[1]["content"] == "done"


class _FrontendStub:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.tool_calls: list[tuple[str, str, str]] = []
        self.stream_tokens: list[tuple[str, str, str]] = []

    async def send_text(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        self.stream_tokens.append((chat_id, agent_name, token))

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        self.tool_calls.append((chat_id, agent_name, tool_name))


class _ChannelStub:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.requests: list[tuple[str, str, str, str]] = []
        self.started = False

    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        self.requests.append((recipient, subject, body, request_id))

    async def poll_reply(self, request_id: str) -> str | None:
        del request_id
        return None

    async def wait_reply(self, request_id: str, timeout: float = 300) -> str:
        del request_id, timeout
        if not self.replies:
            raise AssertionError("No stubbed human reply is available")
        return self.replies.pop(0)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        return None


def _agent(name: str, *responses: str) -> Agent[SingleTurn]:
    return Agent(
        name=name,
        prompt=f"You are {name}.",
        config=TestConfig(*responses),
        response_schema=SingleTurn,
    )


def _prompted_agent(name: str, *responses: str) -> Agent[SingleTurn]:
    return Agent(
        name=name,
        prompt=f"You are {name}.",
        config=TestConfig(*responses),
        response_schema=PromptedSchema(SingleTurn),
    )


def _llm_config() -> LlmConfig:
    cfg = LlmAgentConfig(
        model="test-model",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
    )
    return LlmConfig(pm=cfg, planner=cfg, generator=cfg, evaluator=cfg)


def test_single_runtime_runs_beta_single_flow() -> None:
    frontend = _FrontendStub()
    channel = _ChannelStub(["仓库在 F:/demo"])
    runtime = SingleAgentRuntime(
        chat_id="chat-1",
        frontend=frontend,
        channel=channel,
        llm_config=_llm_config(),
        harness_config=HarnessConfig(max_rounds=4),
        mcp_manager=None,
        skill_registry=None,
        agent_pool=None,
        agent=_agent(
            "Assistant",
            '{"message":"请先提供仓库路径。","next_step":"ask_user"}',
            '{"message":"我已确认仓库路径，并完成本轮任务。","next_step":"complete"}',
        ),
    )

    result = asyncio.run(runtime.run(prompt="帮我检查项目"))

    assert result.status == "completed"
    assert result.last_speaker == "Assistant"
    assert channel.started is True
    assert channel.requests[0][0] == "Assistant"
    assert result.transcript[1]["content"] == "请先提供仓库路径。"
    assert result.transcript[2]["name"] == "assistant_owner"
    assert frontend.messages[-1][1].startswith("【Assistant】")


def test_single_runtime_accepts_prompted_schema_markdown_fences() -> None:
    runtime = SingleAgentRuntime(
        chat_id="chat-2",
        frontend=_FrontendStub(),
        channel=_ChannelStub(["线上环境是 Windows"]),
        llm_config=_llm_config(),
        harness_config=HarnessConfig(max_rounds=3),
        mcp_manager=None,
        skill_registry=None,
        agent_pool=None,
        agent=_prompted_agent(
            "Assistant",
            '```json\n{"message":"请补充部署环境。","next_step":"ask_user"}\n```',
            '{"message":"已收到部署环境信息。","next_step":"complete"}',
        ),
    )

    result = asyncio.run(runtime.run(prompt="继续"))

    assert result.status == "completed"
    assert result.transcript[1]["content"] == "请补充部署环境。"
    assert result.transcript[2]["name"] == "assistant_owner"


def test_single_runtime_plain_text_question_falls_back_to_ask_user() -> None:
    runtime = SingleAgentRuntime(
        chat_id="chat-3",
        frontend=_FrontendStub(),
        channel=_ChannelStub(["回答"]),
        llm_config=_llm_config(),
        harness_config=HarnessConfig(max_rounds=2),
        mcp_manager=None,
        skill_registry=None,
        agent_pool=None,
        agent=Agent(
            name="Assistant",
            prompt="You are Assistant.",
            config=TestConfig("[Assistant] 请告诉我你的项目目录在哪里？", '{"message":"已收到。","next_step":"complete"}'),
        ),
    )

    result = asyncio.run(runtime.run(prompt="你好"))

    assert result.transcript[1]["content"] == "请告诉我你的项目目录在哪里？"
    assert result.transcript[2]["content"] == "回答"
    assert result.status == "completed"
    assert SingleNextStep.ASK_USER.value == "ask_user"
