"""Level 4: Auto Compact — LLM-based conversation summarization.

Uses AG2's built-in ``_reflection_with_llm`` to generate a summary when the
accumulated conversation exceeds a token threshold, then replaces old messages
with the summary while preserving recent context.

This is a ``MessageTransform`` compatible class — add it via ``TransformMessages``
so it hooks into ``process_all_messages_before_reply`` automatically.
"""
from __future__ import annotations

import copy
import logging
import warnings
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default summary prompt (adapted from Claude Code's compact prompt)
# ---------------------------------------------------------------------------
DEFAULT_SUMMARY_PROMPT = """\
Summarize the multi-agent conversation below. The conversation involves \
Planner, Generator, and Evaluator agents collaborating to build a full-stack \
application.

Your summary MUST include:

1. **User Request** — What the user asked to build (preserve original intent).
2. **Plan Summary** — What the Planner decided (architecture, tech stack, features).
3. **Implementation Progress** — Key files created/modified, code patterns, \
architectural decisions. Include file paths and critical code snippets.
4. **Errors & Fixes** — Any errors encountered and how they were resolved.
5. **Evaluation Status** — What the Evaluator found, scores given, issues raised.
6. **Current Task** — What is being worked on right now (be specific about \
which agent is active and what it's doing).
7. **Pending Work** — What still needs to be done.

Be thorough and specific. This summary will replace the original context, \
so include every detail needed to continue the work seamlessly.
"""

# Token overhead buffer — we summarize *before* hitting the hard limit
# so the model still has room to respond.
_SUMMARY_OUTPUT_BUDGET = 4_000
_KEEP_RECENT_MESSAGES = 6  # always keep the last N messages verbatim


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_ENCODER = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """Count tokens in a string using cl100k_base encoding."""
    if not text:
        return 0
    return len(_ENCODER.encode(text))


def _estimate_message_tokens(msg: dict[str, Any]) -> int:
    """Rough token count for a single message dict."""
    content = msg.get("content")
    if isinstance(content, str):
        return _count_tokens(content) + 4  # role + formatting overhead
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    total += _count_tokens(item.get("text", ""))
                else:
                    total += 10  # non-text blocks (images, tool calls…)
            elif isinstance(item, str):
                total += _count_tokens(item)
        return total + 4
    return 4


def _estimate_total_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(_estimate_message_tokens(m) for m in messages)


# ---------------------------------------------------------------------------
# AutoCompactTransform
# ---------------------------------------------------------------------------

class AutoCompactTransform:
    """AG2 ``MessageTransform`` that summarizes old messages via LLM.

    Usage::

        from autogen.agentchat.contrib.capabilities import TransformMessages

        auto_compact = AutoCompactTransform(agent=my_agent, max_tokens=80_000)
        TransformMessages(transforms=[auto_compact]).add_to_agent(my_agent)
    """

    def __init__(
        self,
        agent: Any,
        max_tokens: int = 80_000,
        summary_prompt: str | None = None,
        keep_recent: int = _KEEP_RECENT_MESSAGES,
    ) -> None:
        self._agent = agent
        self._max_tokens = max_tokens
        self._summary_prompt = summary_prompt or DEFAULT_SUMMARY_PROMPT
        self._keep_recent = keep_recent
        self._cached_summary: str | None = None
        self._last_summarized_count: int = 0

    # -- MessageTransform protocol ----------------------------------------

    def apply_transform(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Check token budget; if exceeded, summarize and compress."""
        total_tokens = _estimate_total_tokens(messages)
        threshold = self._max_tokens - _SUMMARY_OUTPUT_BUDGET

        if total_tokens < threshold:
            return messages

        logger.info(
            "AutoCompact triggered: %d tokens >= %d threshold. Summarizing…",
            total_tokens, threshold,
        )
        return self._do_compact(messages)

    def get_logs(
        self,
        pre: list[dict[str, Any]],
        post: list[dict[str, Any]],
    ) -> tuple[str, bool]:
        pre_tok = _estimate_total_tokens(pre)
        post_tok = _estimate_total_tokens(post)
        if post_tok < pre_tok:
            return (
                f"AutoCompact: {pre_tok} → {post_tok} tokens "
                f"(saved {pre_tok - post_tok})",
                True,
            )
        return "AutoCompact: no compression applied.", False

    # -- Core logic -------------------------------------------------------

    def _do_compact(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Generate LLM summary and rebuild message list."""
        summary = self._generate_summary(messages)
        if not summary:
            logger.warning("AutoCompact: LLM returned empty summary — skipping.")
            return messages

        return self._build_compressed(messages, summary)

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """Call LLM via AG2's built-in ``_reflection_with_llm``."""
        try:
            result = self._agent._reflection_with_llm(
                prompt=self._summary_prompt,
                messages=messages,
                llm_agent=self._agent,
            )
            return result or ""
        except Exception:
            logger.warning(
                "AutoCompact: LLM summarization failed.", exc_info=True,
            )
            return ""

    def _build_compressed(
        self,
        messages: list[dict[str, Any]],
        summary: str,
    ) -> list[dict[str, Any]]:
        """Replace old messages with summary, keep recent verbatim."""
        result: list[dict[str, Any]] = []

        # 1) Preserve system message if present
        if messages and messages[0].get("role") == "system":
            result.append(copy.deepcopy(messages[0]))
            messages = messages[1:]

        # 2) Inject the summary as a user message
        result.append({
            "role": "user",
            "content": (
                "[Context Summary — earlier conversation has been compressed]\n\n"
                + summary
            ),
        })

        # 3) Keep the most recent N messages verbatim
        tail = messages[-self._keep_recent :] if len(messages) > self._keep_recent else messages
        result.extend(copy.deepcopy(tail))

        post_tokens = _estimate_total_tokens(result)
        logger.info(
            "AutoCompact complete: %d messages → %d messages, ~%d tokens",
            len(messages) + 1, len(result), post_tokens,
        )
        return result
