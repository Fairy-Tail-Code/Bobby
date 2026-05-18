from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from autogen.beta import Agent, AgentReply, MemoryStream
from autogen.beta.context import Context
from autogen.beta.events import ModelMessageChunk, ToolCallEvent
from pydantic import ValidationError

from agents.beta_factory import create_single_beta_agent
from agents.single_models import SingleNextStep, SingleTurn
from config.config import HarnessConfig, LlmConfig
from fronted.frontend import Frontend
from infrastructure.agent_pool import AgentPool
from infrastructure.channel.channel import ChannelAdapter
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from orchestration.run_result import OrchestrationRunResult

logger = logging.getLogger(__name__)


class _SingleBetaSession:
    def __init__(
        self,
        *,
        agent: Agent[Any],
        frontend: Frontend,
        chat_id: str,
    ) -> None:
        self.agent = agent
        self.frontend = frontend
        self.chat_id = chat_id
        self.stream = _create_compat_memory_stream()
        self.reply: AgentReply[Any, Any] | None = None
        self._sub_ids: list = []
        self._register_observers()

    @property
    def display_name(self) -> str:
        return "Assistant"

    def _register_observers(self) -> None:
        if not self.frontend:
            return
        sub_id = self.stream.where(ModelMessageChunk).subscribe(self._on_model_chunk)
        self._sub_ids.append(sub_id)
        sub_id = self.stream.where(ToolCallEvent).subscribe(self._on_tool_call)
        self._sub_ids.append(sub_id)

    async def _on_model_chunk(
        self,
        event: ModelMessageChunk,
        __ctx__: Context | None = None,
        **kwargs: Any,
    ) -> None:
        del __ctx__, kwargs
        try:
            await self.frontend.stream_token(
                self.chat_id,
                self.display_name,
                event.content,
            )
        except Exception:
            logger.warning(
                "Frontend stream-token notification failed: chat_id=%s role=%s",
                self.chat_id,
                self.display_name,
                exc_info=True,
            )

    async def _on_tool_call(
        self,
        event: ToolCallEvent,
        __ctx__: Context | None = None,
        **kwargs: Any,
    ) -> None:
        del __ctx__, kwargs
        try:
            await self.frontend.on_tool_call(
                self.chat_id,
                self.display_name,
                event.name,
            )
        except Exception:
            logger.warning(
                "Frontend tool-call notification failed: chat_id=%s role=%s tool=%s",
                self.chat_id,
                self.display_name,
                event.name,
                exc_info=True,
            )

    async def ask(self, message: str) -> SingleTurn:
        if self.reply is None:
            self.reply = await self.agent.ask(message, stream=self.stream)
        else:
            self.reply = await self.reply.ask(message)
        return await self._parse_single_turn_reply(self.reply)

    async def _parse_single_turn_reply(
        self,
        reply: AgentReply[Any, Any],
    ) -> SingleTurn:
        current = reply
        last_error: Exception | None = None

        for attempt in range(2):
            body = current.body
            if body is None:
                raise RuntimeError(f"{self.display_name} returned an empty beta-single response")

            try:
                if current is not self.reply:
                    self.reply = current
                return _coerce_single_turn(body)
            except (TypeError, ValueError) as exc:
                last_error = exc
                if attempt >= 1:
                    break
                current = await current.ask(
                    "Your previous response could not be parsed as a valid SingleTurn JSON object.\n"
                    "Return exactly one JSON object with keys `message` and `next_step`.\n"
                    "Valid next_step values are `ask_user`, `complete`, and `terminate`.\n"
                    "Do not wrap the JSON in markdown code fences.\n"
                    "Do not add any explanation outside the JSON object."
                )

        assert last_error is not None
        raise last_error

    def close(self) -> None:
        for sub_id in self._sub_ids:
            self.stream.unsubscribe(sub_id)
        self._sub_ids.clear()


def _create_compat_memory_stream() -> MemoryStream:
    stream = MemoryStream()
    storage = stream.history.storage
    stream._subscribers.clear()

    async def save_event_compat(
        event,
        __ctx__: Context | None = None,
        **kwargs: Any,
    ) -> None:
        del kwargs
        if __ctx__ is None:
            return
        await storage.save_event(event, __ctx__)

    stream.subscribe(save_event_compat)
    return stream


class SingleAgentRuntime:
    """Beta single-agent execution runtime."""

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
        agent: Agent[Any] | None = None,
    ) -> None:
        del agent_pool
        self._chat_id = chat_id
        self._frontend = frontend
        self._channel = channel
        self._harness_config = harness_config
        self._agent = agent or create_single_beta_agent(
            llm_config,
            mcp_manager,
            skill_registry,
            harness_config,
        )
        self._session = _SingleBetaSession(
            agent=self._agent,
            frontend=frontend,
            chat_id=chat_id,
        )
        self._transcript: list[dict[str, Any]] = []

    async def run(
        self,
        *,
        prompt: str,
        resume_messages: list[dict] | None = None,
    ) -> OrchestrationRunResult:
        transcript = [dict(message) for message in (resume_messages or [])]
        self._transcript = transcript

        if resume_messages:
            current_message = self._build_resume_state(prompt, transcript)
        else:
            current_message = prompt
            transcript.append({"role": "user", "name": "user", "content": prompt})

        last_speaker = ""
        status = "terminated"

        try:
            for _ in range(self._harness_config.max_rounds):
                turn = await self._session.ask(current_message)
                last_speaker = self._session.display_name
                transcript.append(
                    {"role": "assistant", "name": last_speaker, "content": turn.message}
                )
                self._transcript = list(transcript)

                if self._frontend:
                    await self._frontend.send_text(
                        self._chat_id,
                        f"【{last_speaker}】\n{turn.message}",
                    )

                if turn.next_step == SingleNextStep.COMPLETE:
                    status = "completed"
                    break

                if turn.next_step == SingleNextStep.TERMINATE:
                    status = "terminated"
                    break

                reply = await self._ask_user(turn.message)
                transcript.append({"role": "user", "name": "assistant_owner", "content": reply})
                current_message = self._format_owner_reply(reply, transcript)
            else:
                if self._frontend:
                    await self._frontend.send_text(
                        self._chat_id,
                        "⚠️ 已达到最大轮次限制，任务被中止。",
                    )
        finally:
            self.close()

        self._transcript = list(transcript)
        return OrchestrationRunResult(
            transcript=transcript,
            last_speaker=last_speaker,
            status=status,
        )

    def get_transcript(self) -> list[dict]:
        return list(self._transcript)

    def close(self) -> None:
        self._session.close()

    async def _ask_user(self, body: str) -> str:
        if self._channel is None:
            raise RuntimeError("No HITL channel is configured for beta-single user questions")

        await self._channel.start()
        request_id = f"harness_{uuid.uuid4().hex[:8]}"
        await self._channel.send(
            "Assistant",
            "Assistant needs your input",
            body,
            request_id,
        )
        return await self._channel.wait_reply(request_id, timeout=self._harness_config.hitl.timeout)

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
    def _build_resume_state(prompt: str, transcript: list[dict[str, Any]]) -> str:
        transcript_text = _format_transcript(transcript)
        return (
            "Continue the single-agent task from this saved transcript.\n\n"
            f"Original prompt:\n{prompt}\n\n"
            f"Saved transcript:\n{transcript_text}\n\n"
            "Resume from the latest state instead of restarting from scratch."
        )

    @staticmethod
    def _format_owner_reply(reply: str, transcript: list[dict[str, Any]]) -> str:
        transcript_text = _format_transcript(transcript)
        return (
            f"Human operator reply:\n{reply}\n\n"
            f"Recent transcript:\n{transcript_text}\n\n"
            "Incorporate the human reply and continue."
        )


def _format_transcript(transcript: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in transcript:
        name = str(message.get("name", message.get("role", "unknown"))).strip() or "unknown"
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"[{name}] {content}")
    return "\n".join(lines) if lines else "(empty transcript)"


def _coerce_single_turn(payload: Any) -> SingleTurn:
    if isinstance(payload, SingleTurn):
        return payload

    if isinstance(payload, dict):
        return SingleTurn.model_validate(payload)

    if isinstance(payload, str):
        candidate = _extract_json_object(payload)
        try:
            return SingleTurn.model_validate_json(candidate)
        except ValidationError:
            inferred = _infer_single_turn_from_plain_text(payload)
            if inferred is not None:
                return inferred
            snippet = payload.strip().replace("\r", " ").replace("\n", " ")
            raise ValueError(
                f"Beta-single agent returned invalid SingleTurn JSON: {snippet[:200]}"
            )

    raise TypeError(f"Unsupported beta-single payload type: {type(payload).__name__}")


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    return match.group(0).strip() if match else stripped


def _infer_single_turn_from_plain_text(text: str) -> SingleTurn | None:
    message = _strip_role_prefix(_extract_json_object(text))
    if not message:
        return None
    return SingleTurn(message=message, next_step=_infer_single_next_step(message))


def _strip_role_prefix(text: str) -> str:
    stripped = text.strip()
    return re.sub(r"^\s*\[[^\]]+\]\s*", "", stripped).strip()


def _infer_single_next_step(text: str) -> SingleNextStep:
    if "?" in text or "？" in text or any(
        marker in text for marker in ("请提供", "请告诉", "请确认", "请补充", "请说明", "是否", "有没有", "什么", "哪些", "哪个", "哪种", "多少", "能否")
    ):
        return SingleNextStep.ASK_USER
    if any(marker in text for marker in ("终止", "停止", "无法继续", "中止")):
        return SingleNextStep.TERMINATE
    return SingleNextStep.COMPLETE
