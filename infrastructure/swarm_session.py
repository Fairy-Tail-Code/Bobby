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
import secrets
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from autogen import ConversableAgent
from autogen.agentchat.group.patterns import DefaultPattern
from autogen.agentchat.group.multi_agent_chat import a_run_group_chat_iter
from autogen.events.agent_events import (
    TextEvent, ToolCallEvent, TerminationEvent,
    RunCompletionEvent, ErrorEvent,
)

from agents.factory import (
    create_pm_agent,
    create_planner_agent,
    create_generator_agent,
    create_evaluator_agent,
    create_single_agent,
    setup_handoffs,
    setup_single_handoffs,
    _register_context_transforms,
)
from agents.channel_proxy import ChannelUserProxyAgent, ROLE_DESCRIPTIONS
from infrastructure.channel.channel import ChannelAdapter
from config.config import HarnessConfig, LlmConfig
from infrastructure.frontend import Frontend
from infrastructure.mcp.manager import McpManager
from infrastructure.session_snapshots import build_snapshot_path
from infrastructure.skills.registry import SkillRegistry
from infrastructure.agent_pool import AgentPool


logger = logging.getLogger(__name__)

_TERMINATE_KEYWORDS = {"终止", "停止", "abort", "cancel", "stop"}


@dataclass
class SessionSnapshot:
    """Structured snapshot of a swarm session for persistence and resume."""

    session_id: str
    chat_id: str
    timestamp: str
    prompt: str
    messages: list[dict]
    max_rounds: int
    status: str  # "terminated" | "completed"
    rounds_used: int

    @staticmethod
    def generate_id() -> str:
        return secrets.token_hex(4)  # 8 hex chars

    def to_dict(self) -> dict:
        return asdict(self)


class SwarmSession:
    """A single swarm session bound to a chat.

    Args:
        chat_id:         Chat ID.
        frontend:        Shared Frontend (e.g. FeishuBotService).
        mcp_manager:     Shared McpManager.
        llm_config:      LLM configuration.
        harness_config:  Harness configuration.
        skill_registry:  Skill registry.
        session_dir:     Directory for saving chat history.
        channel_factory: Callable that creates a ChannelAdapter for a chat_id.
        hitl_mode:       HITL mode string passed to setup_handoffs.
    """

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
        hitl_mode: str = "feishu",
    ) -> None:
        if not session_dir:
            from infrastructure.paths import get_session_dir
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
        self._hitl_mode = hitl_mode
        self._task: asyncio.Task | None = None
        self._channel = channel_factory(chat_id) if channel_factory else None
        self._agents: dict[str, ConversableAgent] = {}
        self._channel_proxies: dict[str, ChannelUserProxyAgent] = {}
        self._terminated = False
        self._prompt: str = ""
        self._is_resume: bool = False
        self._resume_messages: list[dict] = []
        self.owner_open_id: str | None = None  # Session creator, set by SessionManager
        self._on_complete: Callable[[str], None] | None = None  # Cleanup callback

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # --------------------------------------------------------- lifecycle

    def start(self, prompt: str) -> None:
        """Create agents and launch the swarm task."""
        self._prompt = prompt
        self._is_resume = False
        self._task = asyncio.create_task(self._run())
        logger.info("SwarmSession started: chat_id=%s", self.chat_id)

    def start_resume(self, saved_messages: list[dict], prompt: str) -> None:
        """Resume a previous session from saved messages."""
        self._prompt = prompt
        self._resume_messages = saved_messages
        self._is_resume = True
        # start是一个同步方法，为了避免使用async def+await，因为不需要等待_run的结果，只需要在当前事件循环中执行_run就行
        self._task = asyncio.create_task(self._run())
        logger.info("SwarmSession resumed: chat_id=%s", self.chat_id)

    async def _run(self) -> None:
        """Build agents, iterate events from group chat, and push to frontend."""
        try:
            self._agents = self._create_agents()

            if self._mode == "single":
                agents_list = [self._agents["assistant"]]
                for key in ("assistant_owner", "user"):
                    if key in self._agents:
                        agents_list.append(self._agents[key])
                initial_agent = self._agents["assistant"]
            else:
                agents_list = [
                    self._agents["pm"],
                    self._agents["planner"],
                    self._agents["generator"],
                    self._agents["evaluator"],
                ]
                for key in ("pm_owner", "planner_owner", "generator_owner", "evaluator_owner"):
                    if key in self._agents:
                        agents_list.append(self._agents[key])
                initial_agent = self._agents["pm"]

            pattern = DefaultPattern(
                initial_agent=initial_agent,
                agents=agents_list,
            )

            # Choose messages source
            if self._is_resume:
                valid_names = {a.name for a in agents_list}
                messages_input = self._preprocess_resume_messages(
                    self._resume_messages, valid_names,
                )
                if not messages_input:
                    logger.warning(
                        "All resume messages filtered out, falling back to prompt: chat_id=%s",
                        self.chat_id,
                    )
                    messages_input = self._prompt
                    self._is_resume = False
            else:
                messages_input = self._prompt

            # === Event-driven iteration ===
            chat_history: list[dict] = []
            last_speaker_name = ""
            session_id = SessionSnapshot.generate_id()

            async for event_response in await a_run_group_chat_iter(
                pattern=pattern,
                messages=messages_input,
                max_rounds=self._harness_config.max_rounds,
            ):
                event = event_response.content

                if isinstance(event, TextEvent):
                    content = event.content
                    sender = event.sender
                    if content and isinstance(content, str):
                        stripped = content.strip()
                        if (
                            stripped
                            and not re.match(r"^(Transfer to|TERMINATE|APPROVED|REJECTED)", stripped, re.IGNORECASE)
                            and not sender.endswith("_owner")
                        ):
                            await self._frontend.send_text(
                                self.chat_id,
                                f"【{sender}】\n{stripped}",
                            )

                elif isinstance(event, ToolCallEvent):
                    for tc in (event.tool_calls or []):
                        fn_name = tc.get("function", {}).get("name", "unknown")
                        if not fn_name.startswith("transfer_to_") and fn_name != "terminate_command":
                            await self._frontend.on_tool_call(
                                self.chat_id, event.sender, fn_name,
                            )

                elif isinstance(event, RunCompletionEvent):
                    chat_history = event.history
                    last_speaker_name = event.last_speaker
                    self._save_snapshot(
                        messages=chat_history,
                        session_id=session_id,
                        status="completed",
                    )
                    await self._frontend.send_text(
                        self.chat_id,
                        f"✅ 任务完成！最后发言: {last_speaker_name}\n"
                        f"📋 会话ID（可用于恢复）: {session_id}",
                    )

                elif isinstance(event, ErrorEvent):
                    logger.error("Group chat error: %s", event.error)

            # Knowledge collection (fire-and-forget)
            if chat_history:
                await self._collect_and_sync_knowledge(chat_history, session_id)

        except asyncio.CancelledError:
            messages = self._extract_messages_from_agents()
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
        except Exception:
            logger.exception("SwarmSession error: chat_id=%s", self.chat_id)
            await self._frontend.send_text(self.chat_id, "❌ 任务执行出错，请查看日志")
        finally:
            self._terminated = True
            if self._on_complete:
                try:
                    self._on_complete(self.chat_id)
                except Exception:
                    logger.exception("on_complete callback failed: chat_id=%s", self.chat_id)

    def terminate(self) -> None:
        """Cancel the running swarm task."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._terminated = True

    async def dispose(self) -> None:
        """Release all resources held by this session."""
        try:
            self._agents.clear()
            self._channel_proxies.clear()
            self._resume_messages.clear()
            await self._channel.stop()
        except Exception:
            logger.exception("Error disposing session chat_id=%s", self.chat_id)

    async def _collect_and_sync_knowledge(
        self, chat_history: list[dict], session_id: str,
    ) -> None:
        """Collect experiences from chat history and sync to knowledge server."""
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
                    if self._harness_config.tech_stack else None,
                },
            )

            if not experiences:
                return

            local_store = LocalKnowledgeStore(knowledge_config.local_store_path)
            await local_store.connect()
            try:
                enqueued = await local_store.enqueue(experiences)
                logger.info("Enqueued %d experiences (chat_id=%s)", enqueued, self.chat_id)

                sync_client = KnowledgeSyncClient(knowledge_config)
                if await sync_client.health_check():
                    result = await sync_client.sync_with_server(local_store)
                    logger.info(
                        "Knowledge sync: pushed=%d, pulled=%d, errors=%d (chat_id=%s)",
                        result["pushed"], result["pulled"], result["errors"], self.chat_id,
                    )
            finally:
                await local_store.close()
        except Exception:
            logger.exception("Knowledge collection/sync failed (chat_id=%s)", self.chat_id)

    # ---------------------------------------------------- agent creation

    def _create_agents(self) -> dict[str, ConversableAgent]:
        """Create all agents for this session — from pool if available."""
        if self._mode == "single":
            return self._create_single_agents()
        return self._create_swarm_agents()

    def _create_single_agents(self) -> dict[str, ConversableAgent]:
        """Create agents for single mode: one Assistant + one owner proxy."""
        # Use pool if available, otherwise fall back to direct creation
        if self._agent_pool:
            agents = self._agent_pool.acquire_single_agents()
        else:
            agents: dict[str, ConversableAgent] = {
                "assistant": create_single_agent(
                    self._llm_config, self._mcp_manager, self._skill_registry,
                ),
            }

        # Single owner proxy for the assistant
        hitl_cfg = self._harness_config.hitl
        proxy = ChannelUserProxyAgent(
            name="assistant_owner",
            channel=self._channel,
            recipient=self.chat_id,
            role_description=(
                "你是助手负责人，也就是用户本人。助手会向你提问以补充需求、"
                "确认技术方案、或审批风险操作。请根据你的实际需求进行回复。"
            ),
            timeout=hitl_cfg.timeout,
            polling_interval=hitl_cfg.polling_interval,
        )
        agents["assistant_owner"] = proxy
        self._channel_proxies["assistant_owner"] = proxy

        # Context transforms: only needed when NOT using pool (pool templates
        # already have transforms registered on them, and clones inherit hooks)
        if not self._agent_pool and self._harness_config.context.enabled:
            _register_context_transforms(agents["assistant"], self._harness_config.context)

        setup_single_handoffs(agents, self._hitl_mode)
        return agents

    def _create_swarm_agents(self) -> dict[str, ConversableAgent]:
        """Create agents for swarm mode (PM, Planner, Generator, Evaluator)."""
        # Use pool if available, otherwise fall back to direct creation
        if self._agent_pool:
            agents = self._agent_pool.acquire_swarm_agents()
        else:
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
                recipient=self.chat_id,
                role_description=description,
                timeout=hitl_cfg.timeout,
                polling_interval=hitl_cfg.polling_interval,
            )
            agents[role_key] = proxy
            self._channel_proxies[role_key] = proxy

        # Context transforms: only needed when NOT using pool
        if not self._agent_pool and self._harness_config.context.enabled:
            for key in ("pm", "planner", "generator", "evaluator"):
                _register_context_transforms(agents[key], self._harness_config.context)

        setup_handoffs(agents, self._hitl_mode)
        return agents

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

    def _save_snapshot(
        self,
        messages: list[dict],
        session_id: str,
        status: str,
    ) -> None:
        """Save a structured session snapshot for later resume."""
        try:
            # Strip TERMINATE from last message to prevent immediate re-termination on resume
            messages = self._strip_terminate_from_last_message(messages)
            created_at = datetime.now()

            snapshot = SessionSnapshot(
                session_id=session_id,
                chat_id=self.chat_id,
                timestamp=created_at.isoformat(),
                prompt=self._prompt,
                messages=messages,
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
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info("Session snapshot saved: %s (status=%s)", filepath, status)
        except Exception:
            logger.exception("Failed to save session snapshot")

    def _extract_messages_from_agents(self) -> list[dict]:
        """Extract chat history from agent chat_messages.

        In group chat, every agent has a full copy of messages.
        """
        primary_key = "assistant" if self._mode == "single" else "pm"
        primary = self._agents.get(primary_key)
        if not primary:
            return []
        for _other_agent, msgs in primary.chat_messages.items():
            return list(msgs)
        return []

    @staticmethod
    def _preprocess_resume_messages(
        messages: list[dict], valid_names: set[str],
    ) -> list[dict]:
        """Preprocess saved messages for resume compatibility.

        Strips 'name' from messages whose agent name doesn't match
        any agent in the new group chat. This prevents AG2's
        process_initial_messages from raising ValueError on
        unrecognized agent names like 'chat_manager'.
        """
        result = []
        for msg in messages:
            name = msg.get("name", "")
            if name and name not in valid_names:
                # Strip name — AG2 will assign to manager or create temp proxy
                msg = {k: v for k, v in msg.items() if k != "name"}
            result.append(msg)
        return result

    @staticmethod
    def _strip_terminate_from_last_message(messages: list[dict]) -> list[dict]:
        """Remove TERMINATE keyword from last message to allow resume."""
        if not messages:
            return messages
        messages = [dict(m) for m in messages]  # shallow copy
        last = messages[-1]
        content = last.get("content", "")
        if isinstance(content, str):
            content = re.sub(r"\bTERMINATE\b", "", content, flags=re.IGNORECASE).strip()
            last["content"] = content
        return messages
