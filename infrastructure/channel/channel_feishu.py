"""Feishu (Lark) channel adapter — send via REST API, receive via WebSocket long connection.

Prerequisites:
    pip install lark-oapi

Required Feishu app setup:
    1. Create a custom app on https://open.feishu.cn
    2. Enable "Robot" capability
    3. Subscribe to event: "接收消息 im.message.receive_v1"
    4. Set event subscription mode to "长连接" (Long Connection / WebSocket)
    5. Apply for permission: "im:message:send_as_bot" (以应用的身份发消息)
    6. Note the App ID and App Secret
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading

from infrastructure.channel.channel import ChannelAdapter

logger = logging.getLogger(__name__)


class FeishuChannel(ChannelAdapter):
    """Feishu channel using WebSocket long connection for receiving and REST API for sending.

    Args:
        app_id:     App ID from Feishu developer console.
        app_secret: App Secret.
    """

    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._lark_client = None
        self._ws_client = None
        self._ws_thread: threading.Thread | None = None
        self._started = False

        # open_id  -> request_id  (at most one pending request per user)
        self._pending: dict[str, str] = {}
        # request_id -> reply text
        self._replies: dict[str, str] = {}

    # -------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        import lark_oapi as lark

        # Client for sending messages
        self._lark_client = (
            lark.Client.builder()
            .app_id(self._app_id)
            .app_secret(self._app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # Event handler for receiving replies
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )

        # WebSocket client for receiving events (runs in its own thread
        # because its start() manages its own event loop)
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
        logger.info("Feishu WS client started")

    async def stop(self) -> None:
        # The WS thread is a daemon; it dies with the process.
        # No graceful disconnect API available.
        logger.info("Feishu WS client stopping (daemon thread)")

    def _run_ws_in_thread(self) -> None:
        """Run the Feishu WS client in a dedicated thread with its own event loop.

        The lark-oapi WS client internally calls ``loop.run_until_complete()``
        on a module-level loop captured at import time.  If our async app's
        loop is already running (which it is), that call raises
        ``RuntimeError: This event loop is already running``.

        The fix: create a **new** event loop in this thread, override the
        module-level ``loop`` variable, then call ``ws_client.start()``.
        """
        import asyncio
        import lark_oapi.ws.client as ws_mod

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        ws_mod.loop = new_loop  # override the module-level loop

        # Monkey-patch _handle_data_frame to log all incoming data frames
        _orig_handle = self._ws_client._handle_data_frame
        async def _patched_handle(frame):
            try:
                hs = frame.headers
                from lark_oapi.ws.client import _get_by_key
                from lark_oapi.ws.const import HEADER_TYPE
                type_ = _get_by_key(hs, HEADER_TYPE)
                logger.info("Feishu WS data frame received, type=%s, payload_len=%d", type_, len(frame.payload) if frame.payload else 0)
            except Exception:
                pass
            return await _orig_handle(frame)
        self._ws_client._handle_data_frame = _patched_handle

        try:
            self._ws_client.start()
        except Exception:
            logger.exception("Feishu WS client error in background thread")

    # ------------------------------------------------------------------ send

    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        if not self._started:
            await self.start()

        self._pending[recipient] = request_id

        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        # Build a rich text (post) message
        text = (
            f"{subject}\n\n"
            f"{body}\n\n"
            f"---\n"
            f"请直接回复本消息，回复内容将转发给 AI 代理"
        )
        content = json.dumps({"text": text})

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(recipient)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )

        # The lark SDK is synchronous internally; run in thread to avoid blocking
        resp = await asyncio.to_thread(self._lark_client.im.v1.message.create, request)

        if not resp.success():
            raise RuntimeError(
                f"Feishu send failed: code={resp.code}, msg={resp.msg}"
            )
        logger.info("Feishu message sent to %s, request_id=%s", recipient, request_id)

    # ----------------------------------------------------------------- poll

    async def poll_reply(self, request_id: str) -> str | None:
        if request_id in self._replies:
            return self._replies.pop(request_id)
        return None

    # -------------------------------------------------------- event handler

    def _on_message(self, event):
        """Called by Feishu SDK when a message is received (runs in WS thread)."""
        logger.info("Feishu _on_message triggered, event type: %s", type(event).__name__)
        try:
            sender = event.event.sender
            msg = event.event.message

            logger.info(
                "Feishu incoming: chat_type=%s, msg_type=%s, sender_type=%s",
                getattr(msg, "chat_type", "?"),
                getattr(msg, "message_type", "?"),
                getattr(sender, "sender_type", "?"),
            )

            # Ignore messages sent by the bot itself
            if getattr(sender, "sender_type", None) == "app":
                logger.info("Feishu: ignoring bot's own message")
                return

            # Only handle single chat (p2p)
            chat_type = getattr(msg, "chat_type", "")
            if chat_type != "p2p":
                logger.info("Feishu: ignoring non-p2p chat (chat_type=%s)", chat_type)
                return

            open_id = sender.sender_id.open_id
            msg_type = getattr(msg, "message_type", "")

            if msg_type != "text":
                # For non-text messages, just note the type
                reply_text = f"[用户发送了 {msg_type} 类型消息]"
            else:
                raw = json.loads(msg.content)
                reply_text = raw.get("text", "").strip()

            if not reply_text:
                return

            # Match pending request
            if open_id in self._pending:
                request_id = self._pending.pop(open_id)
                self._replies[request_id] = reply_text
                logger.info(
                    "Feishu reply matched: open_id=%s, request_id=%s, text=%s",
                    open_id, request_id, reply_text[:50],
                )
            else:
                logger.warning(
                    "Feishu: no pending request for open_id=%s, pending=%s",
                    open_id, list(self._pending.keys()),
                )
        except Exception:
            logger.exception("Error handling Feishu message event")
