from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from autogen.beta import Agent, AgentReply, MemoryStream
from autogen.beta.events import ToolCallEvent

from agents.network_models import (
    AGENT_ROLE_BY_OWNER,
    ALLOWED_NEXT_STEPS,
    NetworkNextStep,
    NetworkTurn,
    OWNER_ROLE_BY_AGENT,
    ROLE_DISPLAY_NAMES,
)
from infrastructure.channel.channel import ChannelAdapter


@dataclass
class NetworkRunResult:
    transcript: list[dict[str, Any]]
    last_speaker: str
    status: str


class _RoleSession:
    def __init__(
        self,
        *,
        role_key: str,
        agent: Agent[NetworkTurn],
        frontend,
        chat_id: str,
    ) -> None:
        self.role_key = role_key
        self.agent = agent
        self.frontend = frontend
        self.chat_id = chat_id
        self.stream = MemoryStream()
        self.reply: AgentReply[NetworkTurn, NetworkTurn] | None = None
        self._sub_ids: list = []
        self._register_observers()

    @property
    def display_name(self) -> str:
        return ROLE_DISPLAY_NAMES[self.role_key]

    def _register_observers(self) -> None:
        if not self.frontend:
            return
        sub_id = self.stream.where(ToolCallEvent).subscribe(self._on_tool_call)
        self._sub_ids.append(sub_id)

    async def _on_tool_call(self, event: ToolCallEvent, context) -> None:
        del context
        await self.frontend.on_tool_call(
            self.chat_id,
            self.display_name,
            event.name,
        )

    async def ask(self, message: str) -> NetworkTurn:
        if self.reply is None:
            self.reply = await self.agent.ask(message, stream=self.stream)
        else:
            self.reply = await self.reply.ask(message)
        parsed = await self.reply.content(retries=1)
        if parsed is None:
            raise RuntimeError(f"{self.display_name} returned an empty beta-network response")
        return parsed

    def close(self) -> None:
        for sub_id in self._sub_ids:
            self.stream.unsubscribe(sub_id)
        self._sub_ids.clear()


class NetworkSwarmRuntime:
    """Sequential beta-network orchestration for the multi-agent expert mode."""

    def __init__(
        self,
        *,
        agents: dict[str, Agent[NetworkTurn]],
        frontend,
        channel: ChannelAdapter | None,
        chat_id: str,
        max_rounds: int,
        hitl_timeout: int,
    ) -> None:
        self._frontend = frontend
        self._channel = channel
        self._chat_id = chat_id
        self._max_rounds = max_rounds
        self._hitl_timeout = hitl_timeout
        self._roles = {
            key: _RoleSession(
                role_key=key,
                agent=agent,
                frontend=frontend,
                chat_id=chat_id,
            )
            for key, agent in agents.items()
        }

    async def run(
        self,
        *,
        prompt: str,
        resume_messages: list[dict[str, Any]] | None = None,
    ) -> NetworkRunResult:
        transcript = [dict(message) for message in (resume_messages or [])]

        if resume_messages:
            current_role, current_message = self._build_resume_state(prompt, transcript)
        else:
            current_role = "pm"
            current_message = prompt
            transcript.append({"role": "user", "name": "user", "content": prompt})

        last_speaker = ""
        status = "terminated"

        try:
            for _ in range(self._max_rounds):
                role_session = self._roles[current_role]
                turn = await role_session.ask(current_message)
                self._validate_step(current_role, turn.next_step)

                last_speaker = role_session.display_name
                transcript.append(
                    {"role": "assistant", "name": last_speaker, "content": turn.message}
                )

                if self._frontend:
                    await self._frontend.send_text(
                        self._chat_id,
                        f"【{last_speaker}】\n{turn.message}",
                    )

                if turn.next_step == NetworkNextStep.COMPLETE:
                    status = "completed"
                    break

                if turn.next_step == NetworkNextStep.TERMINATE:
                    status = "terminated"
                    break

                if turn.next_step == NetworkNextStep.ASK_USER:
                    owner_role = OWNER_ROLE_BY_AGENT[current_role]
                    reply = await self._ask_user(owner_role, turn.message)
                    transcript.append(
                        {"role": "user", "name": owner_role, "content": reply}
                    )
                    current_message = self._format_owner_reply(owner_role, reply, transcript)
                    current_role = AGENT_ROLE_BY_OWNER[owner_role]
                    continue

                next_role = self._resolve_agent_target(turn.next_step)
                current_message = self._format_handoff(
                    sender_role=current_role,
                    recipient_role=next_role,
                    message=turn.message,
                    transcript=transcript,
                )
                current_role = next_role
            else:
                if self._frontend:
                    await self._frontend.send_text(
                        self._chat_id,
                        "⚠️ 已达到最大轮次限制，任务被中止。",
                    )
        finally:
            self.close()

        return NetworkRunResult(
            transcript=transcript,
            last_speaker=last_speaker,
            status=status,
        )

    def close(self) -> None:
        for role in self._roles.values():
            role.close()

    @staticmethod
    def _validate_step(role_key: str, next_step: NetworkNextStep) -> None:
        if next_step not in ALLOWED_NEXT_STEPS[role_key]:
            allowed = ", ".join(step.value for step in sorted(ALLOWED_NEXT_STEPS[role_key], key=lambda item: item.value))
            raise ValueError(
                f"Role '{role_key}' returned unsupported next_step '{next_step.value}'. "
                f"Allowed values: {allowed}"
            )

    @staticmethod
    def _resolve_agent_target(step: NetworkNextStep) -> str:
        mapping = {
            NetworkNextStep.HANDOFF_PLANNER: "planner",
            NetworkNextStep.HANDOFF_GENERATOR: "generator",
            NetworkNextStep.HANDOFF_EVALUATOR: "evaluator",
        }
        try:
            return mapping[step]
        except KeyError as exc:
            raise ValueError(f"next_step '{step.value}' is not an agent handoff") from exc

    async def _ask_user(self, owner_role: str, body: str) -> str:
        if self._channel is None:
            raise RuntimeError("No HITL channel is configured for beta-network user questions")

        await self._channel.start()
        request_id = f"harness_{uuid.uuid4().hex[:8]}"
        await self._channel.send(
            owner_role,
            f"{owner_role} needs your input",
            body,
            request_id,
        )
        return await self._channel.wait_reply(request_id, timeout=self._hitl_timeout)

    @staticmethod
    def _build_resume_state(
        prompt: str,
        transcript: list[dict[str, Any]],
    ) -> tuple[str, str]:
        last_name = str(transcript[-1].get("name", "")).strip() if transcript else ""
        last_role_key = _name_to_role_key(last_name)
        if last_name in AGENT_ROLE_BY_OWNER:
            current_role = AGENT_ROLE_BY_OWNER[last_name]
        else:
            current_role = last_role_key or "pm"

        transcript_text = _format_transcript(transcript, limit=16)
        message = (
            "Continue the shared multi-agent task from this saved transcript.\n\n"
            f"Original prompt:\n{prompt}\n\n"
            f"Saved transcript:\n{transcript_text}\n\n"
            "Resume from the latest state instead of restarting from scratch."
        )
        return current_role, message

    @staticmethod
    def _format_handoff(
        *,
        sender_role: str,
        recipient_role: str,
        message: str,
        transcript: list[dict[str, Any]],
    ) -> str:
        sender_name = ROLE_DISPLAY_NAMES[sender_role]
        recipient_name = ROLE_DISPLAY_NAMES[recipient_role]
        transcript_text = _format_transcript(transcript, limit=12)
        return (
            f"You are now acting as {recipient_name}.\n\n"
            f"Latest handoff from {sender_name}:\n{message}\n\n"
            f"Recent shared transcript:\n{transcript_text}\n\n"
            "Continue the task from here and choose the next structured step."
        )

    @staticmethod
    def _format_owner_reply(
        owner_role: str,
        reply: str,
        transcript: list[dict[str, Any]],
    ) -> str:
        transcript_text = _format_transcript(transcript, limit=12)
        return (
            f"Human operator reply from {owner_role}:\n{reply}\n\n"
            f"Recent shared transcript:\n{transcript_text}\n\n"
            "Incorporate the human reply and continue."
        )


def _name_to_role_key(name: str) -> str | None:
    normalized = name.strip().lower()
    for role_key, display_name in ROLE_DISPLAY_NAMES.items():
        if normalized == role_key or normalized == display_name.lower():
            return role_key
    return None


def _format_transcript(
    transcript: list[dict[str, Any]],
    *,
    limit: int,
) -> str:
    selected = transcript[-limit:] if limit > 0 else transcript
    lines: list[str] = []
    for message in selected:
        name = str(message.get("name", message.get("role", "unknown"))).strip() or "unknown"
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"[{name}] {content}")
    return "\n".join(lines) if lines else "(empty transcript)"
