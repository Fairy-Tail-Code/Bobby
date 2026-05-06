"""DingTalk channel adapter — send via REST API, receive via Stream (WebSocket).

Prerequisites:
    pip install dingtalk-stream

Required DingTalk app setup:
    1. Create an enterprise internal app on https://open-dev.dingtalk.com
    2. Enable "Robot" capability and select "Stream" message mode
    3. Apply for "企业内机器人发送消息" API permission
    4. Note the Client ID (AppKey), Client Secret (AppSecret), and robot code
"""
from __future__ import annotations

import asyncio
import json
import logging

from infrastructure.channel.channel import ChannelAdapter

logger = logging.getLogger(__name__)


class DingTalkChannel(ChannelAdapter):
    """DingTalk channel using Stream (WebSocket) for receiving and REST API for sending.

    Args:
        client_id:     AppKey / ClientId from DingTalk open platform.
        client_secret: AppSecret / ClientSecret.
        robot_code:    Robot code (usually the same as client_id).
    """

    def __init__(self, client_id: str, client_secret: str, robot_code: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._robot_code = robot_code
        self._stream_client = None
        self._stream_task: asyncio.Task | None = None
        self._started = False

        # user_id  -> request_id  (at most one pending request per user)
        self._pending: dict[str, str] = {}
        # request_id -> reply text
        self._replies: dict[str, str] = {}

    # -------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        import dingtalk_stream

        credential = dingtalk_stream.Credential(self._client_id, self._client_secret)
        self._stream_client = dingtalk_stream.DingTalkStreamClient(credential)
        handler = _ReplyHandler(self)
        self._stream_client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC, handler,
        )
        self._stream_task = asyncio.create_task(self._run_stream())
        logger.info("DingTalk Stream client started")

    async def _run_stream(self) -> None:
        """Background task keeping the WebSocket alive."""
        try:
            await self._stream_client.start()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("DingTalk Stream connection error")

    async def stop(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            logger.info("DingTalk Stream client stopped")

    # ------------------------------------------------------------------ send

    async def send(self, recipient: str, subject: str, body: str, request_id: str) -> None:
        if not self._started:
            await self.start()

        self._pending[recipient] = request_id
        await asyncio.to_thread(self._send_sync, recipient, subject, body)
        logger.info("DingTalk message sent to %s, request_id=%s", recipient, request_id)

    def _send_sync(self, recipient: str, subject: str, body: str) -> None:
        """Blocking HTTP call — runs in a thread via ``asyncio.to_thread``."""
        import requests as http

        token = self._stream_client.get_access_token()
        if not token:
            raise RuntimeError("Failed to obtain DingTalk access_token")

        markdown = (
            f"### {subject}\n\n"
            f"{body}\n\n"
            f"---\n"
            f"请直接回复本消息，回复内容将转发给 AI 代理"
        )

        headers = {
            "Content-Type": "application/json",
            "x-acs-dingtalk-access-token": token,
        }
        payload = {
            "robotCode": self._robot_code,
            "userIds": [recipient],
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"title": subject, "text": markdown}),
        }

        resp = http.post(
            "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

    # ----------------------------------------------------------------- poll

    async def poll_reply(self, request_id: str) -> str | None:
        if request_id in self._replies:
            return self._replies.pop(request_id)
        return None


# ------------------------------------------------------------------ handler

class _ReplyHandler:
    """Registered with ``dingtalk-stream`` to capture user replies."""

    def __init__(self, channel: DingTalkChannel) -> None:
        self._channel = channel

    async def process(self, callback):
        import dingtalk_stream

        msg = dingtalk_stream.ChatbotMessage.from_dict(callback.data)

        # Only handle single-chat messages
        if msg.conversation_type != "1":
            return dingtalk_stream.AckMessage.STATUS_OK, "OK"

        user_id = msg.sender_staff_id
        if not user_id:
            return dingtalk_stream.AckMessage.STATUS_OK, "OK"

        text = msg.text.content.strip() if msg.text and msg.text.content else ""
        if not text:
            return dingtalk_stream.AckMessage.STATUS_OK, "OK"

        # Match: if this user has a pending request, store the reply
        if user_id in self._channel._pending:
            request_id = self._channel._pending.pop(user_id)
            self._channel._replies[request_id] = text
            logger.info("DingTalk reply received from %s, request_id=%s", user_id, request_id)

        return dingtalk_stream.AckMessage.STATUS_OK, "OK"
