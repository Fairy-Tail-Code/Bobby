from __future__ import annotations

import re
import sys

from autogen import ConversableAgent
from autogen.agentchat.group.multi_agent_chat import a_run_group_chat_iter
from autogen.agentchat.group.patterns import DefaultPattern
from autogen.events.agent_events import ErrorEvent, RunCompletionEvent, TextEvent, ToolCallEvent
from autogen.events.client_events import StreamEvent

from agents.channel_proxy import ChannelUserProxyAgent
from agents.factory import _register_context_transforms, create_single_agent, setup_single_handoffs
from config.config import HarnessConfig, LlmConfig
from fronted.frontend import Frontend
from fronted.frontend_cli import CLIFrontend
from infrastructure.agent_pool import AgentPool
from infrastructure.channel.channel import ChannelAdapter
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from orchestration.run_result import OrchestrationRunResult


class SingleAgentRuntime:
    """Legacy single-agent execution runtime kept behind the orchestration layer."""

    def __init__(
        self,
        *,
        chat_id: str,
        frontend: Frontend,
        channel: ChannelAdapter | None,
        llm_config: LlmConfig,
        harness_config: HarnessConfig,
        mcp_manager: McpManager,
        skill_registry: SkillRegistry | None,
        agent_pool: AgentPool | None,
    ) -> None:
        self._chat_id = chat_id
        self._frontend = frontend
        self._channel = channel
        self._llm_config = llm_config
        self._harness_config = harness_config
        self._mcp_manager = mcp_manager
        self._skill_registry = skill_registry
        self._agent_pool = agent_pool
        self._agents: dict[str, ConversableAgent] = {}
        self._transcript: list[dict] = []

    async def run(
        self,
        *,
        prompt: str,
        resume_messages: list[dict] | None = None,
    ) -> OrchestrationRunResult:
        self._agents = self._create_agents()
        agents_list = [self._agents["assistant"]]
        if "assistant_owner" in self._agents:
            agents_list.append(self._agents["assistant_owner"])

        pattern = DefaultPattern(
            initial_agent=self._agents["assistant"],
            agents=agents_list,
        )

        if resume_messages:
            valid_names = {agent.name for agent in agents_list}
            messages_input = self.preprocess_resume_messages(resume_messages, valid_names)
            if not messages_input:
                messages_input = prompt
        else:
            messages_input = prompt

        chat_history: list[dict] = []
        last_speaker_name = ""
        status = "terminated"
        is_cli = isinstance(self._frontend, CLIFrontend)
        streaming_active = False

        async for event_response in a_run_group_chat_iter(
            pattern=pattern,
            messages=messages_input,
            max_rounds=self._harness_config.max_rounds,
        ):
            event = event_response.content

            if isinstance(event, StreamEvent):
                if is_cli:
                    if not streaming_active:
                        sys.stdout.write("\n")
                        streaming_active = True
                    sys.stdout.write(event.content)
                    sys.stdout.flush()
                continue

            if streaming_active:
                streaming_active = False
                if is_cli:
                    sys.stdout.write("\n")
                    sys.stdout.flush()

            if isinstance(event, TextEvent):
                content = event.content
                sender = event.sender
                if content and isinstance(content, str):
                    stripped = content.strip()
                    if self._should_surface_text(sender, stripped):
                        if is_cli:
                            sys.stdout.write(f"  【{sender}】\n")
                            sys.stdout.flush()
                        else:
                            await self._frontend.send_text(
                                self._chat_id,
                                f"【{sender}】\n{stripped}",
                            )

            elif isinstance(event, ToolCallEvent):
                for tool_call in event.tool_calls or []:
                    fn_name = tool_call.get("function", {}).get("name", "unknown")
                    if not fn_name.startswith("transfer_to_") and fn_name != "terminate_command":
                        await self._frontend.on_tool_call(self._chat_id, event.sender, fn_name)

            elif isinstance(event, RunCompletionEvent):
                chat_history = event.history
                self._transcript = list(chat_history)
                last_speaker_name = event.last_speaker
                status = "completed"

            elif isinstance(event, ErrorEvent):
                raise RuntimeError(f"Single-agent runtime failed: {event.error}")

        if not chat_history:
            chat_history = self.get_transcript()

        return OrchestrationRunResult(
            transcript=list(chat_history),
            last_speaker=last_speaker_name,
            status=status,
        )

    def get_transcript(self) -> list[dict]:
        if self._transcript:
            return list(self._transcript)

        primary = self._agents.get("assistant")
        if not primary:
            return []
        for _other_agent, messages in primary.chat_messages.items():
            return list(messages)
        return []

    def _create_agents(self) -> dict[str, ConversableAgent]:
        if self._agent_pool:
            agents = self._agent_pool.acquire_single_agents()
        else:
            agents: dict[str, ConversableAgent] = {
                "assistant": create_single_agent(
                    self._llm_config,
                    self._mcp_manager,
                    self._skill_registry,
                    self._harness_config,
                ),
            }

        hitl_cfg = self._harness_config.hitl
        proxy = ChannelUserProxyAgent(
            name="assistant_owner",
            channel=self._channel,
            recipient=self._chat_id,
            role_description=(
                "你是助手负责人，也就是用户本人。助手会向你提问以补充需求、"
                "确认技术方案、或审批风险操作。请根据你的实际需求进行回复。"
            ),
            timeout=hitl_cfg.timeout,
            polling_interval=hitl_cfg.polling_interval,
        )
        agents["assistant_owner"] = proxy

        if not self._agent_pool and self._harness_config.context.enabled:
            _register_context_transforms(agents["assistant"], self._harness_config.context)

        setup_single_handoffs(agents)
        return agents

    @staticmethod
    def preprocess_resume_messages(
        messages: list[dict],
        valid_names: set[str],
    ) -> list[dict]:
        result = []
        for message in messages:
            name = message.get("name", "")
            if name and name not in valid_names:
                message = {key: value for key, value in message.items() if key != "name"}
            result.append(message)
        return result

    @staticmethod
    def strip_terminate_from_last_message(messages: list[dict]) -> list[dict]:
        if not messages:
            return messages
        copied = [dict(message) for message in messages]
        last = copied[-1]
        content = last.get("content", "")
        if isinstance(content, str):
            last["content"] = re.sub(r"\bTERMINATE\b", "", content, flags=re.IGNORECASE).strip()
        return copied

    @staticmethod
    def _should_surface_text(sender: str, stripped: str) -> bool:
        return (
            bool(stripped)
            and not re.match(r"^(Transfer to|TERMINATE|APPROVED|REJECTED)", stripped, re.IGNORECASE)
            and not sender.endswith("_owner")
        )
