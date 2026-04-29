from __future__ import annotations

from infrastructure.paths import get_agent_prompts_dir


def load_prompt(agent_name: str) -> str:
    """Load a system prompt for an agent from the prompts directory."""
    prompt_path = get_agent_prompts_dir() / f"{agent_name}.md"
    return prompt_path.read_text(encoding="utf-8")
