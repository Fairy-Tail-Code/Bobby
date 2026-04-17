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
from datetime import datetime
from pathlib import Path

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
from infrastructure.channel_feishu_service import ChannelFeishuService
from infrastructure.config import HarnessConfig, LlmConfig
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
        """Build agents, start message monitor, and run swarm."""
        try:
            self._agents = self._create_agents()
            monitor_task = self._start_message_monitor()

            agents_list = [
                self._agents["pm"],
                self._agents["planner"],
                self._agents["generator"],
                self._agents["evaluator"],
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

            # Stop the message monitor now that the swarm is done
            monitor_task.cancel()

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

    def _start_message_monitor(self) -> asyncio.Task:
        """Start a background task that monitors agent messages and pushes to Feishu."""
        return asyncio.create_task(self._monitor_messages())

    async def _monitor_messages(self) -> None:
        """Poll agent message histories and push new messages to Feishu."""
        seen_counts: dict[str, int] = {}

        while not self._terminated:
            for agent_key in ("pm", "planner", "generator", "evaluator"):
                agent = self._agents.get(agent_key)
                if not agent:
                    continue
                for other_agent, msgs in agent.chat_messages.items():
                    pair_key = f"{agent_key}:{getattr(other_agent, 'name', str(other_agent))}"
                    prev_count = seen_counts.get(pair_key, 0)
                    new_msgs = msgs[prev_count:]
                    for msg in new_msgs:
                        await self._push_message_to_feishu(msg)
                    seen_counts[pair_key] = len(msgs)
            await asyncio.sleep(1)

    async def _push_message_to_feishu(self, msg: dict) -> None:
        """Push a single message to Feishu if it's relevant."""
        content = msg.get("content", "")
        role = msg.get("role", "")
        name = msg.get("name", "")

        # Skip tool responses (they have tool_call_id)
        if role == "tool":
            return

        # Skip empty content
        if not content or not isinstance(content, str):
            return
        stripped = content.strip()
        if not stripped:
            return

        # Skip transfer/terminate messages
        if re.match(r"^(Transfer to|TERMINATE|APPROVED|REJECTED)", stripped, re.IGNORECASE):
            return

        # Check for tool calls — show tool name only
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                fn_name = tc.get("function", {}).get("name", "unknown")
                await self._bot.send_text(
                    self.chat_id,
                    f"🔧 **{name}** 正在执行工具: `{fn_name}`",
                )
            return

        # Regular LLM text output
        await self._bot.send_text(
            self.chat_id,
            f"【{name}】\n{stripped}",
        )

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
