from __future__ import annotations

import asyncio
import sys
import threading
import types

from gateway.weixin.channel_weixin_service import ChannelWeixinService
from gateway.weixin.weixin_bot import WeixinBotService

_fake_feishu_bot = types.ModuleType("gateway.feishu.feishu_bot")


class _FakeFeishuBotService:
    async def send_text(self, chat_id: str, text: str) -> None:
        del chat_id, text


_fake_feishu_bot.FeishuBotService = _FakeFeishuBotService
sys.modules.setdefault("gateway.feishu.feishu_bot", _fake_feishu_bot)

from gateway.feishu.channel_feishu_service import ChannelFeishuService


class _DummyBot:
    async def send_text(self, chat_id: str, text: str) -> None:
        del chat_id, text


def _start_background_loop() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    loop = asyncio.new_event_loop()

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return loop, thread


def _stop_background_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


def test_weixin_send_text_switches_back_to_main_loop(monkeypatch) -> None:
    async def _noop_on_message(chat_id: str, open_id: str, chat_type: str, text: str) -> None:
        del chat_id, open_id, chat_type, text

    loop, thread = _start_background_loop()
    try:
        bot = WeixinBotService(account_id="bot", token="token", on_message=_noop_on_message)
        bot.set_main_loop(loop)
        bot._session = object()  # type: ignore[assignment]
        seen: dict[str, object] = {}

        async def fake_send(chat_id: str, text: str) -> None:
            seen["chat_id"] = chat_id
            seen["text"] = text
            seen["loop"] = asyncio.get_running_loop()
            seen["thread_id"] = threading.get_ident()

        monkeypatch.setattr(bot, "_send_text_in_main_loop", fake_send)

        asyncio.run(bot.send_text("chat-1", "hello"))

        assert seen["chat_id"] == "chat-1"
        assert seen["text"] == "hello"
        assert seen["loop"] is loop
        assert seen["thread_id"] == thread.ident
    finally:
        _stop_background_loop(loop, thread)


def test_weixin_stream_token_switches_back_to_main_loop_once(monkeypatch) -> None:
    async def _noop_on_message(chat_id: str, open_id: str, chat_type: str, text: str) -> None:
        del chat_id, open_id, chat_type, text

    loop, thread = _start_background_loop()
    try:
        bot = WeixinBotService(account_id="bot", token="token", on_message=_noop_on_message)
        bot.set_main_loop(loop)
        bot._session = object()  # type: ignore[assignment]
        seen: list[dict[str, object]] = []

        async def fake_send(chat_id: str, text: str) -> None:
            seen.append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "loop": asyncio.get_running_loop(),
                    "thread_id": threading.get_ident(),
                }
            )

        monkeypatch.setattr(bot, "_send_text_in_main_loop", fake_send)

        asyncio.run(bot.stream_token("chat-1", "PM", "你"))
        asyncio.run(bot.stream_token("chat-1", "PM", "好"))

        assert len(seen) == 1
        assert seen[0]["chat_id"] == "chat-1"
        assert seen[0]["text"] == "✍️ 【PM】正在生成回复..."
        assert seen[0]["loop"] is loop
        assert seen[0]["thread_id"] == thread.ident
    finally:
        _stop_background_loop(loop, thread)


def test_weixin_channel_inject_reply_is_thread_safe() -> None:
    loop, thread = _start_background_loop()
    try:
        channel = ChannelWeixinService(_DummyBot(), "chat-1")
        registered = threading.Event()

        async def waiter() -> str:
            future = asyncio.get_running_loop().create_future()
            channel._pending_futures["req-1"] = future
            registered.set()
            return await future

        pending = asyncio.run_coroutine_threadsafe(waiter(), loop)
        assert registered.wait(timeout=2) is True

        assert channel.inject_reply("req-1", "approved") is True
        assert pending.result(timeout=2) == "approved"
    finally:
        _stop_background_loop(loop, thread)


def test_feishu_channel_inject_reply_is_thread_safe() -> None:
    loop, thread = _start_background_loop()
    try:
        channel = ChannelFeishuService(_DummyBot(), "chat-1")
        registered = threading.Event()

        async def waiter() -> str:
            future = asyncio.get_running_loop().create_future()
            channel._pending_futures["req-1"] = future
            registered.set()
            return await future

        pending = asyncio.run_coroutine_threadsafe(waiter(), loop)
        assert registered.wait(timeout=2) is True

        assert channel.inject_reply("req-1", "approved") is True
        assert pending.result(timeout=2) == "approved"
    finally:
        _stop_background_loop(loop, thread)
