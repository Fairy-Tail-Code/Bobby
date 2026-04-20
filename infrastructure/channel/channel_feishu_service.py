"""Feishu channel adapter for service mode.

Unlike the legacy channel_feishu.py (polling-based request-reply),
this adapter pushes messages via FeishuBotService and receives replies
through inject_reply() using asyncio.Future.
"""
from __future__ import annotations

import asyncio
import logging

from infrastructure.channel.channel import ChannelAdapter
from infrastructure.feishu_bot import FeishuBotService

logger = logging.getLogger(__name__)


class ChannelFeishuService(ChannelAdapter):
    """Channel adapter backed by FeishuBotService.

    Uses asyncio.Future for reply injection instead of polling.

    Args:
        bot:     Shared FeishuBotService instance.
        chat_id: Feishu chat ID to send messages to.
    """

    def __init__(self, bot: FeishuBotService, chat_id: str) -> None:
        self._bot = bot
        self._chat_id = chat_id
        # request_id -> Future[str]
        self._pending_futures: dict[str, asyncio.Future[str]] = {}

    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        """Send a message to the Feishu chat and register a Future for the reply."""
        text = f"**{subject}**\n\n{body}"
        # Register future before sending to avoid race
        loop = asyncio.get_running_loop()
        self._pending_futures[request_id] = loop.create_future()
        await self._bot.send_text(self._chat_id, text)

    async def poll_reply(self, request_id: str) -> str | None:
        """Not used in service mode. Returns None always."""
        return None

    async def wait_reply(self, request_id: str, timeout: float = 3600) -> str:
        """Wait for a reply to be injected via inject_reply().

        Returns the reply text, or a timeout message.
        """
        future = self._pending_futures.get(request_id)
        if future is None:
            return "[ERROR] No pending request"

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for reply: request_id=%s", request_id)
            return "[TIMEOUT] 未在规定时间内收到回复，请agent自行判断继续执行。"
        finally:
            self._pending_futures.pop(request_id, None)

    def inject_reply(self, request_id: str, text: str) -> bool:
        """Inject a human reply from Feishu into the pending Future.

        Returns True if the reply was injected, False if no pending request.
        """
        future = self._pending_futures.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(text)
        logger.info("Reply injected for request_id=%s", request_id)
        return True

    @property
    def pending_request_ids(self) -> list[str]:
        return list(self._pending_futures.keys())

    def get_any_pending_request_id(self) -> str | None:
        """Return any pending request_id (for single-user sessions)."""
        for rid, future in self._pending_futures.items():
            if not future.done():
                return rid
        return None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        # Cancel all pending futures
        for future in self._pending_futures.values():
            if not future.done():
                future.cancel()
        self._pending_futures.clear()
