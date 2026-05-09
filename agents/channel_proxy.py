"""Channel-agnostic UserProxyAgent for HITL communication.

Works with any ``ChannelAdapter`` (email, DingTalk, Feishu, etc.) — the agent
doesn't know or care how the message reaches the human or how the reply comes
back.
"""
from __future__ import annotations

import logging
import re
import uuid

from autogen import UserProxyAgent
from autogen.io.base import AsyncInputStream

from infrastructure.channel.channel import ChannelAdapter

logger = logging.getLogger(__name__)

# Patterns to skip when looking for the last meaningful agent message
_SKIP_PATTERNS = [
    r"^Transfer to \w+",
    r"^TERMINATE",
    r"^APPROVED",
    r"^REJECTED",
    r"^\s*$",
]


class ChannelUserProxyAgent(UserProxyAgent):
    """A ``UserProxyAgent`` that communicates with a human via a ``ChannelAdapter``.

    Args:
        name:             Agent name (e.g. "planner_owner").
        channel:          A ``ChannelAdapter`` instance (shared across proxies).
        recipient:        Platform-specific user identifier (email / userId / open_id).
        role_description: System message shown to the agent framework.
        timeout:          Max seconds to wait for a human reply.
        polling_interval: Seconds between poll attempts.
    """

    def __init__(
        self,
        name: str,
        channel: ChannelAdapter,
        recipient: str,
        role_description: str,
        timeout: int = 3600,
        polling_interval: int = 30,
        **kwargs,
    ) -> None:
        super().__init__(
            name=name,
            human_input_mode="ALWAYS",
            system_message=role_description,
            code_execution_config=False,
            llm_config=False,
            description=f"Human operator ({name}) reachable via channel",
            **kwargs,
        )
        self._channel = channel
        self._recipient = recipient
        self._timeout = timeout
        self._polling_interval = polling_interval

    # ------------------------------------------------------------------
    # AG2 hook — called by the framework when it needs human input
    # ------------------------------------------------------------------

    async def a_get_human_input(self, prompt: str, *, iostream: AsyncInputStream | None = None) -> str:
        """Send the agent's question via the channel, then wait for a reply."""
        await self._channel.start()

        context = self._get_last_agent_message()
        request_id = f"harness_{uuid.uuid4().hex[:8]}"

        subject = f"[OpenHarness] {self.name} needs your input"
        body = self._format_body(context)

        await self._channel.send(self._recipient, subject, body, request_id)
        logger.info(
            "Sent to %s (%s), request_id=%s, waiting for reply…",
            self._recipient, self.name, request_id,
        )

        # Delegate to channel's wait_reply (push-based or polling fallback)
        return await self._channel.wait_reply(request_id, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Helpers (channel-agnostic)
    # ------------------------------------------------------------------

    def _get_last_agent_message(self) -> str | None:
        """Find the last meaningful agent message from the GroupChat history."""
        if hasattr(self, "_groupchat") and self._groupchat:
            messages = self._groupchat.messages
        else:
            messages = []
            for msgs in self.chat_messages.values():
                messages.extend(msgs)

        for msg in reversed(messages):
            if msg.get("name") == self.name:
                continue
            content = msg.get("content") or ""
            if not content.strip():
                continue
            if msg.get("role") == "tool":
                continue
            if any(re.search(p, content.strip(), re.IGNORECASE) for p in _SKIP_PATTERNS):
                continue
            sender = msg.get("name", "agent")
            return f"[{sender}]:\n{content}"

        return None

    def _format_body(self, prompt: str | None) -> str:
        text = prompt or "(no context available)"
        return (
            f"A request from the {self.name} requires your input.\n\n"
            f"--- Request Details ---\n"
            f"{text}\n\n"
            f"--- Instructions ---\n"
            f"Please reply directly. Your reply will be forwarded to the AI agent as-is.\n"
        )
