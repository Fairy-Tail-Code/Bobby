from __future__ import annotations

import asyncio
from typing import Any

import autogen

from config.config import LlmAgentConfig


def _extract_text(response: Any, wrapper: autogen.OpenAIWrapper) -> str:
    messages = wrapper.extract_text_or_completion_object(response)
    if not messages:
        return ""

    first = messages[0]
    if isinstance(first, dict):
        content = first.get("content", "")
        return content if isinstance(content, str) else ""
    return first if isinstance(first, str) else ""


async def get_completion_text(
    llm_config: LlmAgentConfig,
    *,
    messages: list[dict[str, str]],
) -> str:
    """Run a simple chat completion and return the first text response."""

    def _run() -> str:
        wrapper = autogen.OpenAIWrapper(**llm_config.to_llm_config())
        response = wrapper.create(messages=messages)
        return _extract_text(response, wrapper).strip()

    return await asyncio.to_thread(_run)
