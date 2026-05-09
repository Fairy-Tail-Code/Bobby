"""Task session shell bound to one chat.

Owns lifecycle, snapshotting, reply injection, and session-level cleanup.
Actual execution lives in orchestration runtimes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable

from infrastructure.channel.channel import ChannelAdapter
from config.config import HarnessConfig, LlmConfig
from fronted.frontend import Frontend
from infrastructure.mcp.manager import McpManager
from infrastructure.session.session_snapshots import build_snapshot_path
from infrastructure.skills.registry import SkillRegistry
from infrastructure.agent_pool import AgentPool
from orchestration.runtime_factory import SessionRuntime, create_session_runtime
from orchestration.single_runtime import SingleAgentRuntime


logger = logging.getLogger(__name__)

_TERMINATE_KEYWORDS = {"终止", "停止", "abort", "cancel", "stop"}


@dataclass
class SessionSnapshot:
    """Structured snapshot of a session for persistence and resume."""

    session_id: str
    chat_id: str
    timestamp: str
    prompt: str
    messages: list[dict]
    max_rounds: int
    status: str
    rounds_used: int

    @staticmethod
    def generate_id() -> str:
        return secrets.token_hex(4)

    def to_dict(self) -> dict:
        return asdict(self)


class AgentSession:
    """Mode-agnostic task session bound to one chat."""

    def __init__(
        self,
        chat_id: str,
        frontend: Frontend,
        mcp_manager: McpManager,
        llm_config: LlmConfig,
        harness_config: HarnessConfig,
        skill_registry: SkillRegistry | None = None,
        session_dir: str = "",
        mode: str | None = None,
        agent_pool: AgentPool | None = None,
        channel_factory: Callable[[str], ChannelAdapter] | None = None,
    ) -> None:
        if not session_dir:
            from utils.paths import get_session_dir

            session_dir = str(get_session_dir())
        self.chat_id = chat_id
        self._frontend = frontend
        self._mcp_manager = mcp_manager
        self._llm_config = llm_config
        self._harness_config = harness_config
        self._skill_registry = skill_registry
        self._session_dir = session_dir
        self._mode = mode or harness_config.mode
        self._agent_pool = agent_pool
        self._task: asyncio.Task | None = None
        self._channel = channel_factory(chat_id) if channel_factory else None
        self._terminated = False
        self._prompt: str = ""
        self._transcript: list[dict] = []
        self._is_resume = False
        self._resume_messages: list[dict] = []
        self._runtime: SessionRuntime | None = None
        self.owner_open_id: str | None = None
        self._on_complete: Callable[[str], None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def transcript(self) -> list[dict]:
        return list(self._transcript)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def channel(self) -> ChannelAdapter | None:
        return self._channel

    @property
    def task(self) -> asyncio.Task | None:
        return self._task

    def set_on_complete(self, callback: Callable[[str], None] | None) -> None:
        self._on_complete = callback

    def start(self, prompt: str) -> None:
        self._prompt = prompt
        self._is_resume = False
        self._task = asyncio.create_task(self._run())
        logger.info("AgentSession started: chat_id=%s mode=%s", self.chat_id, self._mode)

    def start_resume(self, saved_messages: list[dict], prompt: str) -> None:
        self._prompt = prompt
        self._resume_messages = saved_messages
        self._is_resume = True
        self._task = asyncio.create_task(self._run())
        logger.info("AgentSession resumed: chat_id=%s mode=%s", self.chat_id, self._mode)

    async def _run(self) -> None:
        try:
            self._runtime = create_session_runtime(
                mode=self._mode,
                chat_id=self.chat_id,
                frontend=self._frontend,
                channel=self._channel,
                llm_config=self._llm_config,
                harness_config=self._harness_config,
                mcp_manager=self._mcp_manager,
                skill_registry=self._skill_registry,
                agent_pool=self._agent_pool,
            )
            result = await self._runtime.run(
                prompt=self._prompt,
                resume_messages=self._resume_messages if self._is_resume else None,
            )
            self._transcript = list(result.transcript)
            session_id = SessionSnapshot.generate_id()
            self._save_snapshot(
                messages=self._transcript,
                session_id=session_id,
                status=result.status,
            )
            if result.status == "completed":
                await self._frontend.send_text(
                    self.chat_id,
                    f"✅ 任务完成！最后发言: {result.last_speaker}\n"
                    f"📋 会话ID（可用于恢复）: {session_id}",
                )
            else:
                await self._frontend.send_text(
                    self.chat_id,
                    f"⚠️ 任务已终止\n"
                    f"📋 会话ID（可用于恢复）: {session_id}",
                )

            if self._transcript:
                await self._extract_and_persist_memory(
                    self._transcript,
                    session_id,
                    status=result.status,
                )
                await self._collect_and_sync_knowledge(self._transcript, session_id)

        except asyncio.CancelledError:
            messages = list(self._transcript)
            if not messages and self._runtime:
                messages = self._runtime.get_transcript()
            session_id = SessionSnapshot.generate_id()
            self._save_snapshot(
                messages=messages,
                session_id=session_id,
                status="terminated",
            )
            await self._frontend.send_text(
                self.chat_id,
                f"⚠️ 任务已终止\n"
                f"📋 会话ID（可用于恢复）: {session_id}",
            )
            if messages:
                await self._extract_and_persist_memory(messages, session_id, status="terminated")
        except Exception:
            logger.exception("AgentSession error: chat_id=%s mode=%s", self.chat_id, self._mode)
            await self._frontend.send_text(self.chat_id, "❌ 任务执行出错，请查看日志")
        finally:
            self._terminated = True
            self._runtime = None
            if self._on_complete:
                try:
                    self._on_complete(self.chat_id)
                except Exception:
                    logger.exception("on_complete callback failed: chat_id=%s", self.chat_id)

    def terminate(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._terminated = True

    async def dispose(self) -> None:
        try:
            self.terminate()
            self._resume_messages.clear()
            self._transcript.clear()
            if self._channel:
                await self._channel.stop()
        except Exception:
            logger.exception("Error disposing session chat_id=%s", self.chat_id)

    async def _collect_and_sync_knowledge(
        self,
        chat_history: list[dict],
        session_id: str,
    ) -> None:
        knowledge_config = self._harness_config.knowledge
        if not knowledge_config or not knowledge_config.enabled:
            return

        try:
            from infrastructure.knowledge.collector import ExperienceCollector
            from infrastructure.knowledge.local_store import LocalKnowledgeStore
            from infrastructure.knowledge.sync_client import KnowledgeSyncClient

            collector = ExperienceCollector(self._llm_config.generator, knowledge_config)
            experiences = await collector.collect_from_session(
                chat_history=chat_history,
                session_metadata={
                    "prompt": self._prompt,
                    "mode": self._mode,
                    "session_id": session_id,
                    "project_type": "+".join(self._harness_config.tech_stack.values())
                    if self._harness_config.tech_stack
                    else None,
                },
            )

            if not experiences:
                return

            local_store = LocalKnowledgeStore(knowledge_config.local_store_path)
            async with local_store:
                enqueued = await local_store.enqueue(experiences)
                logger.info("Enqueued %d experiences (chat_id=%s)", enqueued, self.chat_id)

                sync_client = KnowledgeSyncClient(knowledge_config)
                if await sync_client.health_check():
                    result = await sync_client.sync_with_server(local_store)
                    logger.info(
                        "Knowledge sync: pushed=%d, pulled=%d, errors=%d (chat_id=%s)",
                        result["pushed"],
                        result["pulled"],
                        result["errors"],
                        self.chat_id,
                    )
        except Exception:
            logger.exception("Knowledge collection/sync failed (chat_id=%s)", self.chat_id)

    async def _extract_and_persist_memory(
        self,
        chat_history: list[dict],
        session_id: str,
        *,
        status: str,
    ) -> None:
        memory_config = self._harness_config.memory
        if not memory_config or not memory_config.enabled or not memory_config.auto_extract_enabled:
            return

        try:
            from infrastructure.memory.extractor import SessionMemoryExtractor

            extractor = SessionMemoryExtractor(self._llm_config.generator, memory_config)
            persisted = await extractor.persist_from_session(
                chat_history=chat_history,
                session_metadata={
                    "prompt": self._prompt,
                    "mode": self._mode,
                    "status": status,
                    "session_id": session_id,
                    "project_type": "+".join(self._harness_config.tech_stack.values())
                    if self._harness_config.tech_stack
                    else None,
                },
            )
            if persisted:
                logger.info(
                    "Persisted %d extracted memories (chat_id=%s, session_id=%s)",
                    len(persisted),
                    self.chat_id,
                    session_id,
                )
        except Exception:
            logger.exception("Automatic memory extraction failed (chat_id=%s)", self.chat_id)

    async def inject_reply(self, text: str) -> bool:
        if self._terminated or self._channel is None:
            return False

        request_id = self._channel.get_any_pending_request_id()
        if request_id:
            return self._channel.inject_reply(request_id, text)

        logger.warning("No pending request in session chat_id=%s", self.chat_id)
        return False

    def _save_snapshot(
        self,
        messages: list[dict],
        session_id: str,
        status: str,
    ) -> None:
        try:
            created_at = datetime.now()
            snapshot = SessionSnapshot(
                session_id=session_id,
                chat_id=self.chat_id,
                timestamp=created_at.isoformat(),
                prompt=self._prompt,
                messages=SingleAgentRuntime.strip_terminate_from_last_message(messages),
                max_rounds=self._harness_config.max_rounds,
                status=status,
                rounds_used=len(messages),
            )
            filepath = build_snapshot_path(
                self._session_dir,
                session_id,
                timestamp=created_at,
            )
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as file:
                json.dump(snapshot.to_dict(), file, ensure_ascii=False, indent=2)
            logger.info("Session snapshot saved: %s (status=%s)", filepath, status)
        except Exception:
            logger.exception("Failed to save session snapshot")
