from __future__ import annotations

import asyncio

from autogen.beta import Agent
from autogen.beta.testing import TestConfig

from agents.network_models import NetworkTurn
from orchestration.network_runtime import NetworkSwarmRuntime
from orchestration.run_result import OrchestrationRunResult


class _FrontendStub:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.tool_calls: list[tuple[str, str, str]] = []

    async def send_text(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        return None

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


def _agent(name: str, *responses: str) -> Agent[NetworkTurn]:
    return Agent(
        name=name,
        prompt=f"You are {name}.",
        config=TestConfig(*responses),
        response_schema=NetworkTurn,
    )


def _plain_agent(name: str, *responses: str) -> Agent[str]:
    return Agent(
        name=name,
        prompt=f"You are {name}.",
        config=TestConfig(*responses),
    )


def test_network_runtime_runs_full_swarm_flow() -> None:
    frontend = _FrontendStub()
    channel = _ChannelStub(["仓库地址是 https://example.com/repo.git"])
    runtime = NetworkSwarmRuntime(
        agents={
            "pm": _agent(
                "PM",
                '{"message":"请先提供仓库地址。","next_step":"ask_user"}',
                '{"message":"PRD 已完成，包含仓库信息和需求边界。","next_step":"handoff_planner"}',
            ),
            "planner": _agent(
                "Planner",
                '{"message":"技术规格已完成，交给 Generator 开始实现。","next_step":"handoff_generator"}',
            ),
            "generator": _agent(
                "Generator",
                '{"message":"实现完成，应用已可供验收。","next_step":"handoff_evaluator"}',
            ),
            "evaluator": _agent(
                "Evaluator",
                '{"message":"EVALUATION PASSED - 所有核心维度已达标。","next_step":"complete"}',
            ),
        },
        frontend=frontend,
        channel=channel,
        chat_id="chat-1",
        max_rounds=8,
        hitl_timeout=30,
    )

    result = asyncio.run(runtime.run(prompt="做一个带记忆系统的多 agent 开发助手"))

    assert isinstance(result, OrchestrationRunResult)
    assert result.status == "completed"
    assert result.last_speaker == "Evaluator"
    assert channel.started is True
    assert channel.requests[0][0] == "pm_owner"
    assert "仓库地址" in channel.requests[0][2]
    assert [item["name"] for item in result.transcript] == [
        "user",
        "PM",
        "pm_owner",
        "PM",
        "Planner",
        "Generator",
        "Evaluator",
    ]
    assert frontend.messages[-1][1].startswith("【Evaluator】")


def test_network_runtime_rejects_invalid_next_step_for_role() -> None:
    runtime = NetworkSwarmRuntime(
        agents={
            "pm": _agent(
                "PM",
                '{"message":"我直接交给 Evaluator。","next_step":"handoff_evaluator"}',
            ),
            "planner": _agent("Planner", '{"message":"unused","next_step":"handoff_generator"}'),
            "generator": _agent("Generator", '{"message":"unused","next_step":"handoff_evaluator"}'),
            "evaluator": _agent("Evaluator", '{"message":"unused","next_step":"complete"}'),
        },
        frontend=_FrontendStub(),
        channel=_ChannelStub([]),
        chat_id="chat-2",
        max_rounds=2,
        hitl_timeout=30,
    )

    try:
        asyncio.run(runtime.run(prompt="invalid route"))
    except ValueError as exc:
        assert "unsupported next_step" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid PM next_step")


def test_network_runtime_parses_plain_json_for_schema_incompatible_backend() -> None:
    runtime = NetworkSwarmRuntime(
        agents={
            "pm": _plain_agent(
                "PM",
                '```json\n{"message":"已确认需求，先结束本轮。","next_step":"terminate"}\n```',
            ),
            "planner": _agent("Planner", '{"message":"unused","next_step":"handoff_generator"}'),
            "generator": _agent("Generator", '{"message":"unused","next_step":"handoff_evaluator"}'),
            "evaluator": _agent("Evaluator", '{"message":"unused","next_step":"complete"}'),
        },
        frontend=_FrontendStub(),
        channel=_ChannelStub([]),
        chat_id="chat-3",
        max_rounds=2,
        hitl_timeout=30,
    )

    result = asyncio.run(runtime.run(prompt="兼容 DeepSeek"))

    assert result.status == "terminated"
    assert result.last_speaker == "PM"
    assert result.transcript[-1]["content"] == "已确认需求，先结束本轮。"
    assert runtime.get_transcript() == result.transcript
