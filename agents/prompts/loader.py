from __future__ import annotations

from pathlib import Path


def load_prompt(agent_name: str) -> str:
    """Load a system prompt for an agent from the prompts directory."""
    prompt_path = Path(__file__).parent / f"{agent_name}.md"
    return prompt_path.read_text(encoding="utf-8")