from __future__ import annotations

import json
import logging
from datetime import datetime

from config.config import KnowledgeConfig, LlmAgentConfig
from utils.llm_completion import get_completion_text

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """Analyze this completed multi-agent development session and extract reusable development experiences.

For each experience, provide a JSON object with:
- title: Short descriptive title (max 500 chars)
- category: One of [problem_solution, code_pattern, agent_decision, architecture, pitfall, user_preference, config_trick]
- tags: List of relevant technology/framework tags
- content: Markdown description (problem + solution + why)
- context: Object with relevant fields like framework, language, tool, error_type

Categories:
- problem_solution: A bug or error that was encountered and resolved
- code_pattern: A reusable code approach or pattern that emerged
- agent_decision: Why an agent chose a particular approach over alternatives
- architecture: A design or architectural decision made
- pitfall: Something that didn't work and what was done instead
- user_preference: A user preference learned from corrections
- config_trick: A non-obvious configuration that solved a problem

Skip:
- Information deducible from code or project structure
- Temporary debugging steps or trivial interactions
- Generic knowledge not specific to this project
- Tool calls, file reads, or transfer messages without insight

Return a JSON array of experience objects. Return empty array if no meaningful experiences found.

Chat history:
{history}"""


class ExperienceCollector:
    """Extracts development experiences from completed chat sessions."""

    def __init__(self, llm_config: LlmAgentConfig, knowledge_config: KnowledgeConfig):
        self._llm_config = llm_config
        self._knowledge_config = knowledge_config

    async def collect_from_session(
        self,
        chat_history: list[dict],
        session_metadata: dict,
    ) -> list[dict]:
        """Extract experiences from a completed chat session using LLM."""
        condensed = self._condense_history(chat_history)
        if not condensed.strip():
            logger.info("No meaningful content in chat history for experience extraction")
            return []

        prompt = _EXTRACTION_PROMPT.format(history=condensed[:50000])

        try:
            content = await get_completion_text(
                self._llm_config,
                messages=[{"role": "user", "content": prompt}],
            )
            if not content:
                logger.warning("Empty response from extraction LLM")
                return []
            experiences = self._parse_response(content, session_metadata)
            logger.info("Extracted %d experiences from session", len(experiences))
            return experiences

        except Exception:
            logger.exception("Failed to extract experiences from session")
            return []

    def _condense_history(self, chat_history: list[dict]) -> str:
        """Filter out noise and keep meaningful messages."""
        meaningful = []
        for msg in chat_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            name = msg.get("name", "")

            # Skip empty or tool-only messages
            if not content or not isinstance(content, str):
                continue

            # Skip pure transfer/handoff messages
            if content.startswith("Transferred") or content.startswith("Transfer to"):
                continue

            # Skip very short messages (likely confirmations)
            if len(content.strip()) < 20:
                continue

            prefix = f"[{name or role}]" if name else f"[{role}]"
            meaningful.append(f"{prefix}: {content[:2000]}")

        return "\n\n".join(meaningful)

    def _parse_response(self, content: str, metadata: dict) -> list[dict]:
        """Parse LLM response into structured experiences."""
        # Try to extract JSON from the response
        text = content.strip()
        if text.startswith("```"):
            # Remove code fences
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON array in the text
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.warning("Could not parse extraction response as JSON")
                    return []
            else:
                logger.warning("No JSON array found in extraction response")
                return []

        if not isinstance(parsed, list):
            return []

        experiences = []
        for item in parsed:
            if not isinstance(item, dict) or "title" not in item or "content" not in item:
                continue
            exp = {
                "title": item["title"][:500],
                "category": item.get("category", "problem_solution"),
                "tags": item.get("tags", []),
                "content": item["content"],
                "context": item.get("context", {}),
                "source_session_id": metadata.get("session_id"),
                "source_agent": item.get("source_agent"),
                "project_type": metadata.get("project_type"),
                "visibility": "private",
                "client_id": self._knowledge_config.client_id,
                "client_timestamp": datetime.now().isoformat(),
            }
            experiences.append(exp)

        return experiences
