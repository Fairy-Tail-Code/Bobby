# 飞书产品化服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AG2 OpenHarness 从 CLI 工具改造为飞书机器人常驻服务，单进程多协程，支持群聊+单聊。

**Architecture:** FastAPI 常驻进程 + 飞书 WebSocket 长连接接收消息。SessionManager 管理多个 SwarmSession，每个 session 独立运行一套 4-agent swarm。通过 agent register_reply hook 拦截消息推送到飞书。Channel proxy 用 asyncio.Future 替代 polling 等待用户回复。

**Tech Stack:** FastAPI, uvicorn, lark-oapi (WS+REST), asyncio, ag2==0.11.5

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `server.py` | Create | 服务入口：FastAPI app、启动 MCP、注册飞书 WS、启动 uvicorn |
| `infrastructure/feishu_bot.py` | Create | 飞书消息收发服务：WS 接收 + REST 发送，支持群聊/单聊 |
| `infrastructure/session_manager.py` | Create | 会话池：创建/查找/终止 SwarmSession |
| `infrastructure/swarm_session.py` | Create | 单个 swarm 会话：agent 创建、消息拦截 hook、生命周期管理 |
| `infrastructure/channel_feishu_service.py` | Create | 新的飞书 ChannelAdapter：send 推送 + inject_reply 注入，替代旧的 polling 模式 |
| `agents/channel_proxy.py` | Modify | `a_get_human_input` 改用 asyncio.Future 等待，不再 polling |
| `agents/factory.py` | Modify | `create_all_agents` 支持传入 `FeishuBotService` 和 `chat_id` 参数 |
| `agents/user.py` | Modify | 新增 `create_feishu_service_proxies` 工厂函数 |

---

### Task 1: FeishuBotService — 飞书消息收发

**Files:**
- Create: `infrastructure/feishu_bot.py`

这个模块封装飞书 WebSocket 接收 + REST API 发送，是所有飞书交互的唯一出口。

- [ ] **Step 1: 创建 `infrastructure/feishu_bot.py`**

```python
"""Feishu bot service — WebSocket receive + REST API send.

Supports both group chat and P2P (single) chat modes.
"""
from __future__ import annotations

import asyncio
import json
import logging
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
                # Feishu replaces @mention with @_user_X format
                import re
                text = re.sub(r"@_user_\d+\s*", "", text).strip()
                if not text:
                    return

            logger.info(
                "Feishu incoming: chat_id=%s, chat_type=%s, open_id=%s, text=%s",
                chat_id, chat_type, open_id, text[:50],
            )

            # Schedule the async callback on the main event loop
            main_loop = _get_main_loop()
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
        # Build post content using Feishu post format
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


# ------------------------------------------------------------------ helpers

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _get_main_loop() -> asyncio.AbstractEventLoop | None:
    return _main_loop
```

- [ ] **Step 2: Commit**

```bash
git add infrastructure/feishu_bot.py
git commit -m "feat: add FeishuBotService for WS receive + REST send"
```

---

### Task 2: ChannelFeishuService — 新的飞书 ChannelAdapter

**Files:**
- Create: `infrastructure/channel_feishu_service.py`

替代旧的 `channel_feishu.py` 的 polling 模式。新的 ChannelAdapter 支持 `send` 推送消息 + `inject_reply` 异步注入回复。

- [ ] **Step 1: 创建 `infrastructure/channel_feishu_service.py`**

```python
"""Feishu channel adapter for service mode.

Unlike the legacy channel_feishu.py (polling-based request-reply),
this adapter pushes messages via FeishuBotService and receives replies
through inject_reply() using asyncio.Future.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

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
```

- [ ] **Step 2: Commit**

```bash
git add infrastructure/channel_feishu_service.py
git commit -m "feat: add ChannelFeishuService with Future-based reply injection"
```

---

### Task 3: 修改 ChannelUserProxyAgent — Future 替代 polling

**Files:**
- Modify: `agents/channel_proxy.py:72-98`

将 `a_get_human_input` 从 polling 循环改为 await Future。需要判断 channel 类型：如果是 `ChannelFeishuService` 则用 `wait_reply`，否则保持原有 polling 逻辑。

- [ ] **Step 1: 修改 `agents/channel_proxy.py`**

在文件顶部添加 import：

```python
from infrastructure.channel.channel_feishu_service import ChannelFeishuService
```

替换 `a_get_human_input` 方法（第 72-98 行）为：

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add agents/channel_proxy.py
git commit -m "feat: ChannelUserProxyAgent supports Future-based reply for service mode"
```

---

### Task 4: SwarmSession — 单个会话封装

**Files:**
- Create: `infrastructure/swarm_session.py`

这是核心组件：封装一套完整的 agents + swarm 运行，管理消息拦截 hook，处理用户回复注入。

- [ ] **Step 1: 创建 `infrastructure/swarm_session.py`**

```python
"""Single swarm session — one per Feishu chat.

Owns a set of agents, runs swarm in an asyncio.Task,
intercepts agent messages and pushes to Feishu,
and injects human replies from Feishu.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from autogen import ConversableAgent
from autogen.agentchat.group.patterns import AutoPattern
from autogen.agentchat.group.multi_agent_chat import a_initiate_group_chat

from agents.factory import (
    create_pm_agent,
    create_planner_agent,
    create_generator_agent,
    create_evaluator_agent,
    setup_handoffs,
    _register_context_transforms,
)
from agents.channel_proxy import ChannelUserProxyAgent, ROLE_DESCRIPTIONS
from infrastructure.channel.channel_feishu_service import ChannelFeishuService
from config.config import (
    HarnessConfig, LlmConfig, HitlConfig, FeishuConfig,
)
from infrastructure.feishu_bot import FeishuBotService
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

_TERMINATE_KEYWORDS = {"终止", "停止", "abort", "cancel", "stop"}


class SwarmSession:
    """A single swarm session bound to a Feishu chat.

    Args:
        chat_id:       Feishu chat ID.
        bot:           Shared FeishuBotService.
        mcp_manager:   Shared McpManager.
        llm_config:    LLM configuration.
        harness_config: Harness configuration.
        skill_registry: Skill registry.
        session_dir:    Directory for saving chat history.
    """

    def __init__(
            self,
            chat_id: str,
            bot: FeishuBotService,
            mcp_manager: McpManager,
            llm_config: LlmConfig,
            harness_config: HarnessConfig,
            skill_registry: SkillRegistry | None = None,
            session_dir: str = "session",
    ) -> None:
        self.chat_id = chat_id
        self._bot = bot
        self._mcp_manager = mcp_manager
        self._llm_config = llm_config
        self._harness_config = harness_config
        self._skill_registry = skill_registry
        self._session_dir = session_dir
        self._task: asyncio.Task | None = None
        self._channel = ChannelFeishuService(bot, chat_id)
        self._agents: dict[str, ConversableAgent] = {}
        self._channel_proxies: dict[str, ChannelUserProxyAgent] = {}
        self._terminated = False
        self._prompt: str = ""

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # --------------------------------------------------------- lifecycle

    def start(self, prompt: str) -> None:
        """Create agents and launch the swarm task."""
        self._prompt = prompt
        self._task = asyncio.create_task(self._run())
        logger.info("SwarmSession started: chat_id=%s", self.chat_id)

    async def _run(self) -> None:
        """Build agents, set up hooks, and run swarm."""
        try:
            self._agents = self._create_agents()
            self._register_message_hooks()

            agents_list = [
                self._agents["planner"],
                self._agents["generator"],
                self._agents["evaluator"],
                self._agents["pm"],
            ]
            for key in ("pm_owner", "planner_owner", "generator_owner", "evaluator_owner"):
                if key in self._agents:
                    agents_list.append(self._agents[key])

            pattern = AutoPattern(
                initial_agent=self._agents["pm"],
                agents=agents_list,
            )

            result, context, last_speaker = await a_initiate_group_chat(
                pattern=pattern,
                messages=self._prompt,
                max_rounds=self._harness_config.max_rounds,
            )

            # Save session
            self._save_session(result.chat_history)

            # Notify user
            await self._bot.send_text(
                self.chat_id,
                f"✅ 任务完成！最后发言: {last_speaker.name}",
            )
        except asyncio.CancelledError:
            await self._bot.send_text(self.chat_id, "⚠️ 任务已终止")
        except Exception:
            logger.exception("SwarmSession error: chat_id=%s", self.chat_id)
            await self._bot.send_text(self.chat_id, "❌ 任务执行出错，请查看日志")
        finally:
            self._terminated = True

    def terminate(self) -> None:
        """Cancel the running swarm task."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._terminated = True

    # ---------------------------------------------------- agent creation

    def _create_agents(self) -> dict[str, ConversableAgent]:
        """Create all agents for this session."""
        agents: dict[str, ConversableAgent] = {
            "pm": create_pm_agent(self._llm_config, self._mcp_manager),
            "planner": create_planner_agent(
                self._llm_config, self._mcp_manager, self._skill_registry,
            ),
            "generator": create_generator_agent(
                self._llm_config, self._mcp_manager, self._skill_registry,
            ),
            "evaluator": create_evaluator_agent(
                self._llm_config, self._mcp_manager, self._skill_registry,
            ),
        }

        # Create per-role channel proxies using the shared channel
        hitl_cfg = self._harness_config.hitl
        for role_key, description in ROLE_DESCRIPTIONS.items():
            proxy = ChannelUserProxyAgent(
                name=role_key,
                channel=self._channel,
                recipient=self.chat_id,  # chat_id as recipient for service mode
                role_description=description,
                timeout=hitl_cfg.timeout,
                polling_interval=hitl_cfg.polling_interval,
            )
            agents[role_key] = proxy
            self._channel_proxies[role_key] = proxy

        # Context transforms for AI agents
        if self._harness_config.context.enabled:
            for key in ("pm", "planner", "generator", "evaluator"):
                _register_context_transforms(agents[key], self._harness_config.context)

        setup_handoffs(agents, "feishu")
        return agents

    # ------------------------------------------------- message interception

    def _register_message_hooks(self) -> None:
        """Register reply hooks on AI agents to push messages to Feishu."""
        ai_agents = ["pm", "planner", "generator", "evaluator"]
        for name in ai_agents:
            agent = self._agents[name]
            agent.register_reply(
                [ConversableAgent, None],
                self._make_intercept_hook(agent),
                position=0,
            )

    def _make_intercept_hook(self, agent: ConversableAgent):
        """Create a reply hook for a specific agent."""

        async def hook(
                recipient: ConversableAgent,
                messages: list[dict] | None = None,
                sender: ConversableAgent | None = None,
                config: Any = None,
        ) -> tuple[bool, str | dict | None]:
            if not messages:
                return False, None

            last_msg = messages[-1]
            content = last_msg.get("content", "")
            msg_name = last_msg.get("name", agent.name)

            # Skip empty, transfer, terminate messages
            if not content or not isinstance(content, str):
                return False, None
            stripped = content.strip()
            if not stripped:
                return False, None
            if re.match(r"^(Transfer to|TERMINATE|APPROVED|REJECTED)", stripped, re.IGNORECASE):
                return False, None

            # Check for tool calls — show tool name only
            tool_calls = last_msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "unknown")
                    await self._bot.send_text(
                        self.chat_id,
                        f"🔧 **{msg_name}** 正在执行工具: `{fn_name}`",
                    )
                return False, None

            # Regular LLM text output — push to Feishu
            await self._bot.send_text(
                self.chat_id,
                f"【{msg_name}】\n{stripped}",
            )
            return False, None

        return hook

    # --------------------------------------------------- reply injection

    async def inject_reply(self, text: str) -> bool:
        """Inject a user reply from Feishu into the session.

        Routes to the channel proxy that is currently waiting.
        """
        if self._terminated:
            return False

        request_id = self._channel.get_any_pending_request_id()
        if request_id:
            return self._channel.inject_reply(request_id, text)

        logger.warning("No pending request in session chat_id=%s", self.chat_id)
        return False

    # --------------------------------------------------- session save

    def _save_session(self, chat_history: list[dict]) -> None:
        """Save chat history to JSON file."""
        try:
            Path(self._session_dir).mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = Path(self._session_dir) / f"chat_history_{self.chat_id}_{timestamp}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(chat_history, f, ensure_ascii=False, indent=2)
            logger.info("Session saved: %s", filepath)
        except Exception:
            logger.exception("Failed to save session")
```

- [ ] **Step 2: Commit**

```bash
git add infrastructure/swarm_session.py
git commit -m "feat: add SwarmSession for per-chat swarm lifecycle management"
```

---

### Task 5: SessionManager — 会话池管理

**Files:**
- Create: `infrastructure/session_manager.py`

管理所有活跃的 SwarmSession，处理新消息的路由（创建/注入/终止）。

- [ ] **Step 1: 创建 `infrastructure/session_manager.py`**

```python
"""Session manager — routes Feishu messages to the right SwarmSession.

One SwarmSession per chat_id. Creates on first message, injects replies
on subsequent messages, terminates on command.
"""
from __future__ import annotations

import logging

from config.config import (
    HarnessConfig, LlmConfig, FeishuConfig,
)
from infrastructure.feishu_bot import FeishuBotService
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from infrastructure.swarm_session import SwarmSession, _TERMINATE_KEYWORDS

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages multiple SwarmSessions keyed by chat_id.

    Args:
        bot:            Shared FeishuBotService.
        mcp_manager:    Shared McpManager.
        llm_config:     LLM configuration.
        harness_config: Harness configuration.
        skill_registry: Skill registry.
        session_dir:    Directory for saving chat history.
    """

    def __init__(
            self,
            bot: FeishuBotService,
            mcp_manager: McpManager,
            llm_config: LlmConfig,
            harness_config: HarnessConfig,
            skill_registry: SkillRegistry | None = None,
            session_dir: str = "session",
    ) -> None:
        self._bot = bot
        self._mcp_manager = mcp_manager
        self._llm_config = llm_config
        self._harness_config = harness_config
        self._skill_registry = skill_registry
        self._session_dir = session_dir
        self._sessions: dict[str, SwarmSession] = {}

    @property
    def active_sessions(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_running)

    async def handle_message(
            self, chat_id: str, open_id: str, chat_type: str, text: str,
    ) -> None:
        """Route an incoming Feishu message.

        - New chat or no active session → create session with text as prompt
        - Terminate keyword → kill the session
        - Otherwise → inject reply into active session
        """
        stripped = text.strip()

        # Check for terminate command
        if stripped.lower() in _TERMINATE_KEYWORDS:
            session = self._sessions.get(chat_id)
            if session and session.is_running:
                session.terminate()
                del self._sessions[chat_id]
                logger.info("Session terminated: chat_id=%s", chat_id)
            else:
                await self._bot.send_text(chat_id, "当前没有进行中的任务")
            return

        session = self._sessions.get(chat_id)

        if session and session.is_running:
            # Active session — inject user reply
            injected = await session.inject_reply(stripped)
            if not injected:
                # No pending request — tell user
                await self._bot.send_text(
                    chat_id,
                    "当前正在处理中，请等待 AI 代理提问后再回复。",
                )
        else:
            # No active session — create one with user's message as prompt
            await self._create_session(chat_id, stripped)

    async def _create_session(self, chat_id: str, prompt: str) -> None:
        """Create a new SwarmSession and start it."""
        session = SwarmSession(
            chat_id=chat_id,
            bot=self._bot,
            mcp_manager=self._mcp_manager,
            llm_config=self._llm_config,
            harness_config=self._harness_config,
            skill_registry=self._skill_registry,
            session_dir=self._session_dir,
        )
        self._sessions[chat_id] = session
        session.start(prompt)
        await self._bot.send_text(chat_id, f"🚀 任务已启动: {prompt[:100]}")

    def terminate_all(self) -> None:
        """Terminate all active sessions (for graceful shutdown)."""
        for session in self._sessions.values():
            session.terminate()
        self._sessions.clear()
```

- [ ] **Step 2: Commit**

```bash
git add infrastructure/session_manager.py
git commit -m "feat: add SessionManager for routing messages to SwarmSessions"
```

---

### Task 6: server.py — 服务入口

**Files:**
- Create: `server.py`

FastAPI 应用入口，启动时初始化 MCP、飞书连接，注册消息回调，运行 uvicorn。

- [ ] **Step 1: 创建 `server.py`**

```python
"""AG2 OpenHarness Feishu Service — FastAPI entry point.

Usage:
    python server.py
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from config.config import (
    load_llm_config, load_mcp_config, load_harness_config,
    load_feishu_config,
)
from infrastructure.feishu_bot import FeishuBotService, set_main_loop
from infrastructure.mcp.manager import McpManager
from infrastructure.session_manager import SessionManager
from infrastructure.skills.registry import SkillRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent
CONFIG_DIR = PROJECT_DIR / "config"


async def main() -> None:
    """Initialize all services and run forever."""
    # 1. Load configs
    logger.info("Loading configs...")
    llm_config = load_llm_config(PROJECT_DIR)
    mcp_config = load_mcp_config(CONFIG_DIR)
    harness_config = load_harness_config(CONFIG_DIR)
    feishu_config = load_feishu_config(PROJECT_DIR)

    # 2. Set main event loop reference for WS thread → main loop bridge
    set_main_loop(asyncio.get_running_loop())

    # 3. Initialize skill registry
    skills_dir = PROJECT_DIR / "skills"
    skill_registry = SkillRegistry(roots=[skills_dir])
    logger.info("Available skills: %s", [s.name for s in skill_registry.list_skills()])

    # 4. Connect MCP servers
    logger.info("Connecting to MCP servers...")
    mcp_manager = McpManager()
    connected_servers: list[str] = []
    for server_cfg in mcp_config.servers:
        try:
            await mcp_manager.connect(server_cfg)
            connected_servers.append(server_cfg.name)
        except Exception as e:
            logger.error("Failed to connect MCP server '%s': %s", server_cfg.name, e)

    skill_registry.connected_servers = connected_servers
    for issue in skill_registry.validate_alignment():
        logger.warning(
            "Skill '%s' needs MCP servers %s but %s not connected",
            issue.skill_name, issue.missing_servers, issue.missing_servers,
        )

    # 5. Get session dir from config
    config_data = {}
    import yaml
    config_path = CONFIG_DIR / "harness.yaml"
    if config_path.exists():
        config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    session_dir = config_data.get("harness", {}).get("session", {}).get("session_dir", "session")

    # 6. Create SessionManager
    session_manager = SessionManager(
        bot=None,  # Will set after creating FeishuBotService
        mcp_manager=mcp_manager,
        llm_config=llm_config,
        harness_config=harness_config,
        skill_registry=skill_registry,
        session_dir=session_dir,
    )

    # 7. Create and start FeishuBotService
    bot = FeishuBotService(
        app_id=feishu_config.app_id,
        app_secret=feishu_config.app_secret,
        on_message=session_manager.handle_message,
    )
    session_manager._bot = bot
    bot.start()

    logger.info(
        "🚀 AG2 OpenHarness Feishu Service started. "
        "Active MCP servers: %s",
        connected_servers,
    )

    # 8. Run forever until interrupted
    try:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _signal_handler():
            logger.info("Shutdown signal received")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        await stop_event.wait()
    finally:
        logger.info("Shutting down...")
        session_manager.terminate_all()
        await mcp_manager.disconnect_all()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add server.py
git commit -m "feat: add server.py entry point for Feishu service"
```

---

### Task 7: 集成测试 — 手动验证

**Files:**
- Modify: `.env` (用户手动配置)
- Modify: `config/harness.yaml` (确保 mode 正确)

这一步没有自动化测试（飞书集成需要真实 bot），而是手动验证清单。

- [ ] **Step 1: 确认 .env 配置**

确保 `.env` 中有以下配置：

```env
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
```

- [ ] **Step 2: 确认 harness.yaml**

确保 `config/harness.yaml` 中 `hitl.mode` 为 `feishu`：

```yaml
  hitl:
    mode: feishu
```

- [ ] **Step 3: 启动服务**

```bash
cd AG2_openharness
python server.py
```

预期输出：
```
🚀 AG2 OpenHarness Feishu Service started. Active MCP servers: [...]
```

- [ ] **Step 4: 飞书测试**

1. 在飞书中找到机器人，发送 `帮我写一个 Hello World 网页`
2. 预期：收到 `🚀 任务已启动` 消息，然后看到 `【PM】` 消息
3. 回复 PM 的提问，验证回复能被注入到 swarm
4. 发送 `终止`，验证任务被终止
5. 再次发送新任务，验证新 session 能正常创建

- [ ] **Step 5: Commit (如有修复)**

```bash
git add -A
git commit -m "fix: integration fixes from manual testing"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ 常驻服务器运行 → `server.py` + asyncio.run forever
- ✅ 单进程多协程 → 每个 SwarmSession 是独立的 asyncio.Task
- ✅ 保留多角色 HITL → `ROLE_DESCRIPTIONS` + `setup_handoffs(agents, "feishu")`
- ✅ 用户可见全部 agent 对话 → `_register_message_hooks` + `register_reply`
- ✅ 工具调用显示"正在执行" → hook 中检测 `tool_calls` key
- ✅ 支持群聊和单聊 → `FeishuBotService._on_ws_message` 处理两种 chat_type
- ✅ 隐式路由（有 session 当回复，没有当新任务）→ `SessionManager.handle_message`
- ✅ 终止任务 → `terminate()` 取消 asyncio.Task
- ✅ 不考虑用户注册 → 无认证逻辑

**Placeholder scan:** 无 TBD、TODO 或模糊描述。

**Type consistency:**
- `ChannelFeishuService` 在 Task 2 定义，Task 3 的 `isinstance` 检查匹配
- `SwarmSession` 在 Task 4 中使用 `ChannelFeishuService`，属性名一致
- `SessionManager.handle_message` 签名与 `FeishuBotService.on_message` 回调签名匹配
