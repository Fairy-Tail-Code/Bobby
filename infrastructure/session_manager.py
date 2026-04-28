"""Session manager — routes Feishu messages to the right SwarmSession.

One SwarmSession per chat_id. Creates on first message, injects replies
on subsequent messages, terminates on command, and supports session resume.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

from config.config import HarnessConfig, LlmConfig
from infrastructure.feishu_bot import FeishuBotService
from infrastructure.mcp.manager import McpManager
from infrastructure.paths import get_session_dir
from infrastructure.session_snapshots import find_snapshot_path, iter_snapshot_paths
from infrastructure.skills.registry import SkillRegistry
from infrastructure.swarm_session import SwarmSession, _TERMINATE_KEYWORDS

logger = logging.getLogger(__name__)

_RESUME_PATTERN = re.compile(r"^harness\s+resume\s+([0-9a-fA-F]{8})$", re.IGNORECASE)
_LIST_PATTERN = re.compile(r"^harness\s+list$", re.IGNORECASE)
_MODE_NORMAL_PATTERN = re.compile(r"^harness\s+(?:mode\s+)?(?:normal|普通|普通模式)$", re.IGNORECASE)
_MODE_EXPERT_PATTERN = re.compile(r"^harness\s+(?:mode\s+)?(?:expert|专家|专家模式|swarm)$", re.IGNORECASE)

_RESTART_PATTERN = re.compile(r"^harness\s+restart$", re.IGNORECASE)


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
        bot: FeishuBotService | None,
        mcp_manager: McpManager,
        llm_config: LlmConfig,
        harness_config: HarnessConfig,
        skill_registry: SkillRegistry | None = None,
        session_dir: str = "",
        restart_event: asyncio.Event | None = None,
    ) -> None:
        if not session_dir:
            session_dir = str(get_session_dir())
        self._bot = bot
        self._mcp_manager = mcp_manager
        self._llm_config = llm_config
        self._harness_config = harness_config
        self._skill_registry = skill_registry
        self._session_dir = session_dir
        self._restart_event = restart_event
        self._sessions: dict[str, SwarmSession] = {}
        self._chat_modes: dict[str, str] = {}  # chat_id -> "swarm" | "single"

    @property
    def active_sessions(self) -> int:
        return sum(1 for s in self._sessions.values() if s.is_running)

    async def handle_message(
        self, chat_id: str, open_id: str, chat_type: str, text: str,
    ) -> None:
        """Route an incoming Feishu message.

        - Mode switch command → set mode for this chat
        - Terminate keyword → kill the session
        - "harness resume <id>" → resume a saved session
        - "harness list" → list resumable sessions
        - Active session → inject reply
        - Otherwise → create new session with text as prompt
        """
        stripped = text.strip()

        # Check for mode switch commands
        if _MODE_NORMAL_PATTERN.match(stripped):
            self._chat_modes[chat_id] = "single"
            await self._bot.send_text(chat_id, "已切换到普通模式 (单 Agent)")
            return
        if _MODE_EXPERT_PATTERN.match(stripped):
            self._chat_modes[chat_id] = "swarm"
            await self._bot.send_text(chat_id, "已切换到专家模式 (多 Agent 协作)")
            return

        # Check for restart command: "harness restart"
        if _RESTART_PATTERN.match(stripped):
            self.terminate_all()
            if self._bot:
                await self._bot.send_text(chat_id, "🔄 服务正在重启...")
            if self._restart_event:
                self._restart_event.set()
            return

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

        # Check for resume command: "harness resume <session_id>"
        resume_match = _RESUME_PATTERN.match(stripped)
        if resume_match:
            session_id = resume_match.group(1).lower()
            await self._resume_session(chat_id, session_id)
            return

        # Check for list command: "harness list"
        if _LIST_PATTERN.match(stripped):
            await self._list_sessions(chat_id)
            return


        session = self._sessions.get(chat_id)

        if session and session.is_running:
            # Group chat: only session creator can reply (swarm mode only)
            if (
                chat_type == "group"
                and session._mode != "single"
                and session.owner_open_id
                and open_id != session.owner_open_id
            ):
                await self._bot.send_text(
                    chat_id,
                    "只有任务发起者可以回复，请联系发起者或发送'终止'结束任务。",
                )
                return
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
            await self._create_session(chat_id, stripped, open_id=open_id, chat_type=chat_type)

    async def _create_session(self, chat_id: str, prompt: str, *, open_id: str = "", chat_type: str = "p2p") -> None:
        """Create a new SwarmSession and start it."""
        # Clean up any old completed session
        old = self._sessions.get(chat_id)
        if old:
            old.terminate()
            await old._channel.stop()

        mode = self._chat_modes.get(chat_id, self._harness_config.mode)

        session = SwarmSession(
            chat_id=chat_id,
            bot=self._bot,
            mcp_manager=self._mcp_manager,
            llm_config=self._llm_config,
            harness_config=self._harness_config,
            skill_registry=self._skill_registry,
            session_dir=self._session_dir,
            mode=mode,
        )
        # Record session owner for group chat access control (swarm mode only)
        if mode != "single" and chat_type == "group" and open_id:
            session.owner_open_id = open_id
        self._sessions[chat_id] = session
        session.start(prompt)

        mode_label = "普通模式" if mode == "single" else "专家模式"
        await self._bot.send_text(chat_id, f"🚀 任务已启动 ({mode_label}): {prompt[:100]}")

    async def _resume_session(self, chat_id: str, session_id: str) -> None:
        """Load a saved session snapshot and resume it in a new SwarmSession."""
        snapshot_path = find_snapshot_path(self._session_dir, session_id)
        if snapshot_path is None:
            await self._bot.send_text(chat_id, f"未找到会话ID: {session_id}")
            return

        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snapshot_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load session snapshot %s: %s", session_id, e)
            await self._bot.send_text(chat_id, "会话数据损坏，无法恢复")
            return

        saved_messages = snapshot_data.get("messages", [])
        original_prompt = snapshot_data.get("prompt", "(恢复的会话)")
        original_status = snapshot_data.get("status", "unknown")

        if not saved_messages:
            await self._bot.send_text(chat_id, "会话无消息记录，无法恢复")
            return

        # Clean up any existing session for this chat_id
        old = self._sessions.get(chat_id)
        if old:
            old.terminate()
            await old._channel.stop()

        # Create new session and start in resume mode (no owner check for resume)
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
        session.start_resume(saved_messages, original_prompt)

        msg_count = len(saved_messages)
        await self._bot.send_text(
            chat_id,
            f"🔄 会话已恢复 (ID: {session_id}, 之前状态: {original_status})\n"
            f"已加载 {msg_count} 条消息，继续执行...",
        )
        logger.info(
            "Session resumed: chat_id=%s, session_id=%s, messages=%d",
            chat_id, session_id, msg_count,
        )

    async def _list_sessions(self, chat_id: str) -> None:
        """List all available session snapshots."""
        session_dir = Path(self._session_dir)
        if not session_dir.exists():
            await self._bot.send_text(chat_id, "暂无保存的会话")
            return

        snapshots = []
        for path in iter_snapshot_paths(session_dir):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("session_id", "?")
                ts = data.get("timestamp", "?")
                status = data.get("status", "?")
                msg_count = len(data.get("messages", []))
                prompt_preview = data.get("prompt", "")[:50]
                snapshots.append(f"- {sid} | {status} | {ts[:19]} | {msg_count}条消息 | {prompt_preview}")
            except Exception:
                continue

        if not snapshots:
            await self._bot.send_text(chat_id, "暂无保存的会话")
            return

        header = f"📋 找到 {len(snapshots)} 个会话:\n\n"
        # Limit to last 10 sessions to avoid message too long
        body = "\n".join(snapshots[:10])
        if len(snapshots) > 10:
            body += f"\n\n... 还有 {len(snapshots) - 10} 个会话"
        await self._bot.send_text(chat_id, header + body)

    def terminate_all(self) -> None:
        """Terminate all active sessions (for graceful shutdown)."""
        for session in self._sessions.values():
            session.terminate()
        self._sessions.clear()
