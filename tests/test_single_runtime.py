from __future__ import annotations

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
