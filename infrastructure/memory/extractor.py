from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from config.config import LlmAgentConfig, MemoryConfig
from infrastructure.memory.index import read_memory_index_for_prompt
from infrastructure.memory.store import load_memory_document, save_memory_file
from infrastructure.memory.types import MemoryDocument, MemoryType
from utils.llm_completion import get_completion_text

logger = logging.getLogger(__name__)

_MAX_HISTORY_CHARS = 50_000
_MAX_MESSAGE_CHARS = 2_000
_CODE_FENCE_RE = re.compile(r"^```(?:json|markdown)?\s*|\s*```$", re.IGNORECASE)
_VALID_MEMORY_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_EXTRACTION_PROMPT = """Analyze this completed agent session and extract durable long-term memories.

Return a JSON array. Each item must be an object with:
- name: kebab-case memory name. Reuse an existing memory name when updating a related memory from the current index.
- memory_type: one of [user, feedback, project, reference]
- description: one-line summary for MEMORY.md (max 160 chars)
- content: markdown body only, without YAML frontmatter

Only extract knowledge that is durable and not reliably derivable from code, files, or git history:
- `user`: user profile, preferences, long-term constraints, working style
- `feedback`: corrections about how the agent should behave in future sessions
- `project`: project decisions, durable status, ownership, milestones, process rules
- `reference`: stable external links, dashboards, docs, ticket systems, environment pointers

Skip:
- transitory task progress
- code that already exists in the repository
- one-off debugging noise
- tool-call chatter or handoff messages
- anything too vague to be useful next time

Prefer updating an existing memory over creating a duplicate when the current index already contains a matching topic.
Extract at most {max_memories} memories.
Return [] if nothing should be stored.

Current memory index:
{memory_index}

Session metadata:
{metadata}

Chat history:
{history}
"""

_MERGE_PROMPT = """You are merging a newly extracted durable memory into an existing memory document.

Return exactly one JSON object with:
- should_write: boolean
- memory_type: one of [user, feedback, project, reference]
- description: one-line summary for MEMORY.md (max 160 chars)
- content: markdown body only, without YAML frontmatter

Rules:
- Preserve still-valid durable facts from the existing memory.
- Integrate genuinely new durable information from the candidate memory.
- Remove or replace stale/conflicting details when the candidate clearly supersedes them.
- Keep the memory concise and reusable in future sessions.
- If the candidate adds nothing meaningful and the existing memory should remain unchanged, return should_write=false and reuse the existing effective content.
- Do not invent details not present in either input.

Existing memory document:
{existing_memory}

Candidate extracted memory:
{candidate_memory}
"""


@dataclass(slots=True)
class ExtractedMemory:
    name: str
    memory_type: MemoryType
    description: str
    content: str


@dataclass(slots=True)
class ResolvedMemoryWrite:
    name: str
    memory_type: MemoryType
    description: str
    content: str
    should_write: bool = True


class SessionMemoryExtractor:
    """Extract durable memories from completed sessions and persist them."""

    def __init__(self, llm_config: LlmAgentConfig, memory_config: MemoryConfig):
        self._llm_config = llm_config
        self._memory_config = memory_config

    async def extract_from_session(
        self,
        chat_history: list[dict],
        session_metadata: dict,
    ) -> list[ExtractedMemory]:
        if self._memory_config.max_auto_memories <= 0:
            return []

        condensed = self._condense_history(chat_history)
        if not condensed.strip():
            logger.info("No meaningful chat history for memory extraction")
            return []

        prompt = _EXTRACTION_PROMPT.format(
            max_memories=self._memory_config.max_auto_memories,
            memory_index=read_memory_index_for_prompt(self._memory_config),
            metadata=json.dumps(session_metadata, ensure_ascii=False, indent=2),
            history=condensed[:_MAX_HISTORY_CHARS],
        )

        try:
            content = await get_completion_text(
                self._llm_config,
                messages=[{"role": "user", "content": prompt}],
            )
            if not content:
                logger.warning("Empty response from memory extractor LLM")
                return []
            memories = self._parse_response(content)
            logger.info("Extracted %d durable memories from session", len(memories))
            return memories
        except Exception:
            logger.exception("Failed to extract durable memories from session")
            return []

    async def persist_from_session(
        self,
        chat_history: list[dict],
        session_metadata: dict,
    ) -> list[Path]:
        extracted = await self.extract_from_session(chat_history, session_metadata)
        if not extracted:
            return []

        persisted: list[Path] = []
        seen_names: set[str] = set()
        for memory in extracted:
            if memory.name in seen_names:
                continue
            seen_names.add(memory.name)

            try:
                resolved = await self._resolve_memory_write(memory)
                if not resolved.should_write:
                    continue
                path = save_memory_file(
                    name=resolved.name,
                    content=resolved.content,
                    memory_type=resolved.memory_type.value,
                    description=resolved.description,
                    memory_config=self._memory_config,
                )
            except ValueError:
                logger.warning("Skipping invalid extracted memory '%s'", memory.name, exc_info=True)
                continue
            persisted.append(path)
        return persisted

    async def _resolve_memory_write(self, memory: ExtractedMemory) -> ResolvedMemoryWrite:
        try:
            existing = load_memory_document(memory.name, self._memory_config)
        except FileNotFoundError:
            return ResolvedMemoryWrite(
                name=memory.name,
                memory_type=memory.memory_type,
                description=memory.description,
                content=memory.content,
            )

        merged = await self._merge_with_existing(memory, existing)
        if merged is None:
            return ResolvedMemoryWrite(
                name=memory.name,
                memory_type=existing.record.memory_type,
                description=existing.record.description,
                content=existing.body,
                should_write=False,
            )

        if self._is_same_as_existing(existing, merged):
            return ResolvedMemoryWrite(
                name=memory.name,
                memory_type=merged.memory_type,
                description=merged.description,
                content=merged.content,
                should_write=False,
            )
        return merged

    async def _merge_with_existing(
        self,
        memory: ExtractedMemory,
        existing: MemoryDocument,
    ) -> ResolvedMemoryWrite | None:
        prompt = _MERGE_PROMPT.format(
            existing_memory=existing.raw_text,
            candidate_memory=json.dumps(
                {
                    "name": memory.name,
                    "memory_type": memory.memory_type.value,
                    "description": memory.description,
                    "content": memory.content,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        try:
            content = await get_completion_text(
                self._llm_config,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            logger.exception("Failed to merge extracted memory '%s' with existing document", memory.name)
            return ResolvedMemoryWrite(
                name=memory.name,
                memory_type=memory.memory_type,
                description=memory.description,
                content=memory.content,
            )

        if not content:
            return None
        return self._parse_merge_response(memory.name, content)

    @staticmethod
    def _condense_history(chat_history: list[dict]) -> str:
        meaningful: list[str] = []
        for msg in chat_history:
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            stripped = content.strip()
            if not stripped:
                continue
            if stripped.startswith("Transferred") or stripped.startswith("Transfer to"):
                continue
            if len(stripped) < 20:
                continue

            name = msg.get("name", "") or msg.get("role", "unknown")
            meaningful.append(f"[{name}]: {stripped[:_MAX_MESSAGE_CHARS]}")
        return "\n\n".join(meaningful)

    @staticmethod
    def _parse_response(content: str) -> list[ExtractedMemory]:
        text = (content or "").strip()
        if text.startswith("```"):
            text = _CODE_FENCE_RE.sub("", text).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                logger.warning("No JSON array found in memory extraction response")
                return []
            try:
                parsed = json.loads(text[start:end])
            except json.JSONDecodeError:
                logger.warning("Could not parse memory extraction response as JSON")
                return []

        if not isinstance(parsed, list):
            return []

        memories: list[ExtractedMemory] = []
        for item in parsed:
            memory = SessionMemoryExtractor._coerce_memory(item)
            if memory is not None:
                memories.append(memory)
        return memories

    @staticmethod
    def _parse_merge_response(name: str, content: str) -> ResolvedMemoryWrite | None:
        parsed = SessionMemoryExtractor._parse_json_payload(content)
        if not isinstance(parsed, dict):
            return None

        should_write = parsed.get("should_write", True)
        description = parsed.get("description")
        body = parsed.get("content")
        memory_type = parsed.get("memory_type")
        if not isinstance(should_write, bool):
            should_write = True
        if not all(isinstance(value, str) for value in (description, body, memory_type)):
            return None

        normalized_description = " ".join(description.strip().split())[:160]
        normalized_body = body.strip()
        if not normalized_description or not normalized_body:
            return None

        try:
            return ResolvedMemoryWrite(
                name=name,
                memory_type=MemoryType.coerce(memory_type),
                description=normalized_description,
                content=normalized_body,
                should_write=should_write,
            )
        except ValueError:
            return None

    @staticmethod
    def _parse_json_payload(content: str) -> object | None:
        text = (content or "").strip()
        if text.startswith("```"):
            text = _CODE_FENCE_RE.sub("", text).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            array_start = text.find("[")
            array_end = text.rfind("]") + 1
            if array_start >= 0 and array_end > array_start:
                try:
                    return json.loads(text[array_start:array_end])
                except json.JSONDecodeError:
                    pass

            obj_start = text.find("{")
            obj_end = text.rfind("}") + 1
            if obj_start >= 0 and obj_end > obj_start:
                try:
                    return json.loads(text[obj_start:obj_end])
                except json.JSONDecodeError:
                    return None
        return None

    @staticmethod
    def _is_same_as_existing(existing: MemoryDocument, resolved: ResolvedMemoryWrite) -> bool:
        return (
            existing.record.memory_type == resolved.memory_type
            and existing.record.description == resolved.description
            and existing.body.strip() == resolved.content.strip()
        )

    @staticmethod
    def _coerce_memory(item: object) -> ExtractedMemory | None:
        if not isinstance(item, dict):
            return None

        name = item.get("name")
        description = item.get("description")
        content = item.get("content")
        memory_type = item.get("memory_type")
        if not all(isinstance(value, str) for value in (name, description, content, memory_type)):
            return None

        normalized_name = name.strip().removesuffix(".md")
        normalized_description = " ".join(description.strip().split())[:160]
        normalized_content = content.strip()
        if not normalized_name or not normalized_description or not normalized_content:
            return None
        if not _VALID_MEMORY_NAME_RE.fullmatch(normalized_name):
            return None

        try:
            return ExtractedMemory(
                name=normalized_name,
                memory_type=MemoryType.coerce(memory_type),
                description=normalized_description,
                content=normalized_content,
            )
        except ValueError:
            return None
