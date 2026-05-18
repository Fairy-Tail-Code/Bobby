"""Weixin channel adapter for gateway service mode."""
from __future__ import annotations

import asyncio
import logging

from infrastructure.channel.channel import ChannelAdapter
from gateway.weixin.weixin_bot import WeixinBotService

logger = logging.getLogger(__name__)


class ChannelWeixinService(ChannelAdapter):
    """Channel adapter backed by WeixinBotService using reply injection."""

    def __init__(self, bot: WeixinBotService, chat_id: str) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._pending_futures: dict[str, asyncio.Future[str]] = {}

    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        del recipient
        text = f"【{subject}】\n\n{body}"
        logger.info("Sand Message")
        loop = asyncio.get_running_loop()
        self._pending_futures[request_id] = loop.create_future()
        await self._bot.send_text(self._chat_id, text)

    async def poll_reply(self, request_id: str) -> str | None:
        del request_id
        return None

    async def wait_reply(self, request_id: str, timeout: float = 3600) -> str:
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
        future = self._pending_futures.get(request_id)
        if future is None or future.done():
            return False
        loop = future.get_loop()
        if loop.is_closed():
            return False
        loop.call_soon_threadsafe(self._set_future_result, future, text)
        logger.info("Reply injected for request_id=%s", request_id)
        return True

    @staticmethod
    def _set_future_result(future: asyncio.Future[str], text: str) -> None:
        if not future.done():
            future.set_result(text)

    @property
    def pending_request_ids(self) -> list[str]:
        return list(self._pending_futures.keys())

    def get_any_pending_request_id(self) -> str | None:
        for request_id, future in self._pending_futures.items():
            if not future.done():
                return request_id
        return None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        for future in self._pending_futures.values():
            if not future.done():
                loop = future.get_loop()
                if not loop.is_closed():
                    loop.call_soon_threadsafe(self._cancel_future, future)
        self._pending_futures.clear()

    @staticmethod
    def _cancel_future(future: asyncio.Future[str]) -> None:
        if not future.done():
            future.cancel()
