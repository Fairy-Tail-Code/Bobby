"""Channel-agnostic UserProxyAgent for HITL communication.

Works with any ``ChannelAdapter`` (email, DingTalk, Feishu, etc.) — the agent
doesn't know or care how the message reaches the human or how the reply comes
back.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid

from autogen import UserProxyAgent
from autogen.io.base import AsyncInputStream

from infrastructure.channel import ChannelAdapter
from infrastructure.channel_feishu_service import ChannelFeishuService

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

        # Use Future-based wait for service mode, polling for legacy mode
        if isinstance(self._channel, ChannelFeishuService):
            return await self._channel.wait_reply(request_id, timeout=self._timeout)

        # Legacy polling path (email, dingtalk, old feishu)
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            reply = await self._channel.poll_reply(request_id)
            if reply is not None:
                logger.info("Reply received from %s (%s)", self._recipient, self.name)
                return reply
            await asyncio.sleep(self._polling_interval)

        logger.warning("Timeout waiting for reply from %s (%s)", self._recipient, self.name)
        return "[TIMEOUT] 未在规定时间内收到回复，请agent自行判断继续执行。"

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


# ------------------------------------------------------------------
# Role descriptions (shared across all channel types)
# ------------------------------------------------------------------

ROLE_DESCRIPTIONS = {
    "pm_owner": (
        "你是 PM 负责人，也就是用户本人。PM agent 会向你提问以补充和澄清需求细节，"
        "也会将 PRD 草稿发给你确认。请根据你的实际需求进行补充、修改或确认。"
    ),
    "planner_owner": (
        "你是 Planner 负责人。当 Planner agent 遇到需求不明确、信息不足时，"
        "会向你提问。请补充需求细节或澄清模糊之处。"
    ),
    "generator_owner": (
        "你是 Generator 负责人。当 Generator agent 准备执行风险操作"
        "（如删除数据库、强制推送、修改生产配置等）时，需要你的审批。"
        "回复 'approve' 表示批准，回复其他内容表示拒绝或提出修改意见。"
    ),
    "evaluator_owner": (
        "你是 Evaluator 负责人。当 Evaluator agent 在审核过程中需要确认"
        "某些决策或标准时，会向你咨询。请提供你的判断和意见。"
    ),
}


def create_channel_proxies(
    channel: ChannelAdapter,
    recipients: dict[str, str],
    timeout: int = 3600,
    polling_interval: int = 30,
) -> dict[str, ChannelUserProxyAgent]:
    """Create one ``ChannelUserProxyAgent`` per role.

    Args:
        channel:          Shared ``ChannelAdapter`` instance.
        recipients:       Mapping of ``short_role`` → platform user ID.
                          e.g. ``{"planner": "user123", "generator": "user456"}``
        timeout:          Reply timeout in seconds.
        polling_interval: Poll interval in seconds.

    Returns:
        Dict keyed by role name (e.g. "planner_owner").
    """
    proxies: dict[str, ChannelUserProxyAgent] = {}
    for role_key, description in ROLE_DESCRIPTIONS.items():
        short_role = role_key.replace("_owner", "")
        recipient = recipients.get(short_role, "")
        if not recipient:
            logger.warning("No recipient configured for %s, skipping", role_key)
            continue
        proxies[role_key] = ChannelUserProxyAgent(
            name=role_key,
            channel=channel,
            recipient=recipient,
            role_description=description,
            timeout=timeout,
            polling_interval=polling_interval,
        )
        logger.info("Created channel proxy %s -> %s", role_key, recipient)
    return proxies
