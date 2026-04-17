"""Feishu bot service — WebSocket receive + REST API send.

Supports both group chat and P2P (single) chat modes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from typing import Callable, Awaitable

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)

logger = logging.getLogger(__name__)


class FeishuBotService:
    """Singleton-like service that manages the Feishu WS connection and sends messages.

    Args:
        app_id:     Feishu app ID.
        app_secret: Feishu app secret.
        on_message: Async callback invoked when a user message arrives.
                    Signature: async (chat_id, open_id, chat_type, text) -> None
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        on_message: Callable[[str, str, str, str], Awaitable[None]],
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._on_message = on_message
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._lark_client: lark.Client | None = None
        self._ws_client: lark.ws.Client | None = None
        self._ws_thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        """Initialize lark client and start WS listener thread."""
        if self._started:
            return
        self._started = True

        self._lark_client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_ws_message)
            .build()
        )

        self._ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )

        self._ws_thread = threading.Thread(
            target=self._run_ws_in_thread, daemon=True,
        )
        self._ws_thread.start()
        logger.info("FeishuBotService WS client started")

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the main event loop reference for cross-thread coroutine scheduling."""
        self._main_loop = loop

    def _run_ws_in_thread(self) -> None:
        import lark_oapi.ws.client as ws_mod

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        ws_mod.loop = new_loop

        try:
            self._ws_client.start()
        except Exception:
            logger.exception("FeishuBotService WS client error")

    def _on_ws_message(self, event) -> None:
        """Called by Feishu SDK in WS thread when a message arrives."""
        try:
            sender = event.event.sender
            msg = event.event.message

            # Ignore bot's own messages
            if getattr(sender, "sender_type", None) == "app":
                return

            chat_id = getattr(msg, "chat_id", "")
            chat_type = getattr(msg, "chat_type", "")
            open_id = sender.sender_id.open_id
            msg_type = getattr(msg, "message_type", "")

            if msg_type != "text":
                if self._main_loop and self._main_loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._send_message(chat_id, "text", json.dumps({"text": "暂不支持该消息类型，请发送文字消息。"})),
                        self._main_loop,
                    )
                return

            raw = json.loads(msg.content)
            text = raw.get("text", "").strip()
            if not text:
                return

            # In group chat, only respond when @mentioned
            if chat_type == "group":
                mentions = getattr(msg, "mentions", None) or []
                if not mentions:
                    return
                # Strip @mention prefix from text
                text = re.sub(r"@_user_\d+\s*", "", text).strip()
                if not text:
                    return

            logger.info(
                "Feishu incoming: chat_id=%s, chat_type=%s, open_id=%s, text=%s",
                chat_id, chat_type, open_id, text[:50],
            )

            # Schedule the async callback on the main event loop
            main_loop = self._main_loop
            if main_loop and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._on_message(chat_id, open_id, chat_type, text),
                    main_loop,
                )
        except Exception:
            logger.exception("Error in FeishuBotService._on_ws_message")

    # ---------------------------------------------------------------- send

    async def send_text(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat (group or P2P)."""
        content = json.dumps({"text": text})
        await self._send_message(chat_id, "text", content)

    async def send_rich_text(self, chat_id: str, title: str, content_lines: list[str]) -> None:
        """Send a rich text (post) message with title and content."""
        lines = []
        for line in content_lines:
            lines.append([{"tag": "text", "text": line}])
        post = {
            "zh_cn": {
                "title": title,
                "content": lines,
            }
        }
        content = json.dumps({"post": post})
        await self._send_message(chat_id, "post", content)

    async def _send_message(self, chat_id: str, msg_type: str, content: str) -> None:
        if not self._lark_client:
            raise RuntimeError("FeishuBotService not started")

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )

        resp = await asyncio.to_thread(
            self._lark_client.im.v1.message.create, request,
        )
        if not resp.success():
            logger.error(
                "Feishu send failed: code=%s, msg=%s", resp.code, resp.msg,
            )
        else:
            logger.info("Feishu message sent to chat_id=%s", chat_id)
