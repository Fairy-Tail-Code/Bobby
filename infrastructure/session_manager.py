"""Session manager — routes Feishu messages to the right SwarmSession.

One SwarmSession per chat_id. Creates on first message, injects replies
on subsequent messages, terminates on command.
"""
from __future__ import annotations

import logging

from infrastructure.config import HarnessConfig, LlmConfig
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
        bot: FeishuBotService | None,
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
        # Clean up any old completed session
        old = self._sessions.get(chat_id)
        if old:
            old.terminate()
            await old._channel.stop()

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
