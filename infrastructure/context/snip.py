"""Level 1: Snip Compact — message history trimming.

Thin wrapper around AG2's built-in ``MessageHistoryLimiter``.
It keeps only the most recent N messages, optionally preserving the first
user message so the original request is never lost.

Usage::

    from infrastructure.context.snip import create_snip_transform

    snip = create_snip_transform(max_messages=60)
    snip.add_to_agent(my_agent)
"""
from __future__ import annotations

from autogen.agentchat.contrib.capabilities.transform_messages import TransformMessages
from autogen.agentchat.contrib.capabilities.transforms import MessageHistoryLimiter


def create_snip_transform(
    max_messages: int = 60,
    keep_first_message: bool = True,
    exclude_names: list[str] | None = None,
) -> TransformMessages:
    """Create a Level 1 snip transform using AG2's MessageHistoryLimiter.

    Args:
        max_messages: Maximum number of messages to retain.
        keep_first_message: Always keep the initial user request message.
        exclude_names: Agent names whose messages should be excluded before
            applying the limit.
    """
    limiter = MessageHistoryLimiter(
        max_messages=max_messages,
        keep_first_message=keep_first_message,
        exclude_names=exclude_names,
    )
    return TransformMessages(transforms=[limiter])
