"""Weixin bot service backed by Tencent iLink long polling."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Coroutine

try:
    import aiohttp
except ImportError:  # pragma: no cover - dependency gate
    aiohttp = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class WeixinBotService:
    """Minimal Weixin gateway service for text-based chat sessions."""

    MAX_TEXT_LENGTH = 1800

    def __init__(
        self,
        account_id: str,
        token: str,
        on_message: Callable[[str, str, str, str], Awaitable[None]],
        *,
        base_url: str | None = None,
    ) -> None:
        self._account_id = account_id
        self._token = token
        self._base_url = base_url
        self._on_message = on_message
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._started = False
        self._session: "aiohttp.ClientSession | None" = None
        self._sync_buf = ""
        self._context_tokens: dict[str, str] = {}
        self._recent_message_ids: dict[str, float] = {}

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._main_loop = loop

    def start(self) -> None:
        # 懒加载
        from gateway.weixin.weixin_onboard import (
            check_weixin_requirements,
            ILINK_BASE_URL,
        )

        if self._started:
            return
        if not check_weixin_requirements():
            raise RuntimeError("Weixin runtime requires aiohttp")
        if self._main_loop is None:
            raise RuntimeError("Main event loop not set")
        if self._base_url is None:
            self._base_url = ILINK_BASE_URL
        self._base_url = self._base_url.rstrip("/")
        self._started = True
        self._poll_task = self._main_loop.create_task(self._poll_loop())
        logger.info("WeixinBotService polling started")

    def stop(self) -> None:
        self._started = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None
        logger.info("WeixinBotService stopping")

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._run_on_main_loop(self._send_text_in_main_loop(chat_id, text))

    async def _run_on_main_loop(self, coroutine: Coroutine[Any, Any, None]) -> None:
        if self._main_loop is None:
            raise RuntimeError("Main event loop not set")
        current_loop = asyncio.get_running_loop()
        if current_loop is self._main_loop:
            await coroutine
            return
        if not self._main_loop.is_running():
            raise RuntimeError("Main event loop not running")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._main_loop)
        await asyncio.wrap_future(future)

    async def _send_text_in_main_loop(self, chat_id: str, text: str) -> None:
        if not self._session:
            raise RuntimeError("WeixinBotService not started")
        chunks = [text[i:i + self.MAX_TEXT_LENGTH] for i in range(0, len(text), self.MAX_TEXT_LENGTH)] or [text]
        for chunk in chunks:
            await self._send_text_chunk(chat_id, chunk)

    async def _send_text_chunk(self, chat_id: str, text: str) -> None:
        from gateway.weixin.weixin_onboard import send_text_message

        if not self._session:
            raise RuntimeError("WeixinBotService not started")
        context_token = self._context_tokens.get(chat_id)
        client_id = f"openharness-weixin-{uuid.uuid4().hex}"
        response = await send_text_message(
            self._session,
            base_url=self._base_url,
            token=self._token,
            to_user_id=chat_id,
            text=text,
            client_id=client_id,
            context_token=context_token,
        )
        ret = response.get("ret")
        errcode = response.get("errcode")
        if ret not in (None, 0) or errcode not in (None, 0):
            if context_token and (ret == -14 or errcode == -14 or (ret == -2 and str(response.get("errmsg", "")).lower() == "unknown error")):
                self._context_tokens.pop(chat_id, None)
                response = await send_text_message(
                    self._session,
                    base_url=self._base_url,
                    token=self._token,
                    to_user_id=chat_id,
                    text=text,
                    client_id=f"openharness-weixin-{uuid.uuid4().hex}",
                    context_token=None,
                )
                ret = response.get("ret")
                errcode = response.get("errcode")
            if ret not in (None, 0) or errcode not in (None, 0):
                raise RuntimeError(
                    f"Weixin send failed: ret={ret} errcode={errcode} errmsg={response.get('errmsg') or response.get('msg') or 'unknown'}"
                )

    async def stream_token(self, chat_id: str, agent_name: str, token: str) -> None:
        del chat_id, agent_name, token

    async def on_tool_call(self, chat_id: str, agent_name: str, tool_name: str) -> None:
        await self.send_text(chat_id, f"🔧 【{agent_name}】正在执行工具：{tool_name}")

    async def _poll_loop(self) -> None:
        from gateway.weixin.weixin_onboard import (
            AIOHTTP_AVAILABLE,
            get_updates,
        )

        if not AIOHTTP_AVAILABLE or aiohttp is None:
            return
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                self._session = session
                while self._started:
                    response = await get_updates(
                        session,
                        base_url=self._base_url,
                        token=self._token,
                        sync_buf=self._sync_buf,
                    )
                    self._sync_buf = str(response.get("get_updates_buf") or self._sync_buf or "")
                    for message in response.get("msgs") or []:
                        await self._handle_message(message)
                    self._prune_recent_messages()
                    await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            logger.info("WeixinBotService polling cancelled")
        except Exception:
            logger.exception("WeixinBotService polling error")
        finally:
            self._session = None

    async def _handle_message(self, message: dict) -> None:
        from gateway.weixin.weixin_onboard import extract_text, guess_chat_type

        sender_id = str(message.get("from_user_id") or "").strip()
        if not sender_id or sender_id == self._account_id:
            return

        if int(message.get("message_type") or 0) == 2:
            return

        message_id = str(message.get("msg_id") or message.get("client_id") or "")
        if message_id and message_id in self._recent_message_ids:
            return
        if message_id:
            self._recent_message_ids[message_id] = asyncio.get_running_loop().time()

        text = extract_text(message.get("item_list") or []).strip()
        if not text:
            return

        chat_type, chat_id = guess_chat_type(message, self._account_id)
        if not chat_id:
            return

        context_token = str(message.get("context_token") or "").strip()
        if context_token:
            self._context_tokens[chat_id] = context_token

        logger.info(
            "Weixin incoming: chat_id=%s, chat_type=%s, sender_id=%s, text=%s",
            chat_id,
            chat_type,
            sender_id,
            text[:50],
        )
        await self._on_message(chat_id, sender_id, chat_type, text)

    def _prune_recent_messages(self) -> None:
        from gateway.weixin.weixin_onboard import MESSAGE_DEDUP_TTL_SECONDS

        now = asyncio.get_running_loop().time()
        expired = [
            key for key, timestamp in self._recent_message_ids.items()
            if now - timestamp >= MESSAGE_DEDUP_TTL_SECONDS
        ]
        for key in expired:
            self._recent_message_ids.pop(key, None)
