from __future__ import annotations

from autogen.beta.events import ModelMessage, ModelRequest, ModelResponse, ToolCallEvent, ToolCallsEvent, ToolResultEvent, ToolResultsEvent

from infrastructure.context.beta_limiters import trim_beta_history_by_chars, trim_beta_history_by_events


def _tool_pair_events():
    call = ToolCallEvent(id="call-1", name="read_file", arguments='{"path":"README.md"}')
    return [
        ModelRequest(content="initial request"),
        ModelResponse(tool_calls=ToolCallsEvent(calls=[call])),
        ToolResultsEvent(results=[ToolResultEvent.from_call(call, "file content")]),
        ModelResponse(message=ModelMessage(content="final answer")),
    ]


def test_trim_beta_history_by_events_keeps_tool_call_and_result_paired() -> None:
    trimmed = trim_beta_history_by_events(_tool_pair_events()[:-1], max_events=2)

    assert len(trimmed) == 3
    assert isinstance(trimmed[1], ModelResponse)
    assert isinstance(trimmed[2], ToolResultsEvent)


def test_trim_beta_history_by_chars_keeps_tool_call_and_result_paired() -> None:
    trimmed = trim_beta_history_by_chars(_tool_pair_events()[:-1], max_chars=80)

    assert isinstance(trimmed[1], ModelResponse)
    assert isinstance(trimmed[2], ToolResultsEvent)
