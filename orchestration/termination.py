from __future__ import annotations

from typing import Any, Callable


def create_termination_check() -> Callable[[dict[str, Any]], bool]:
    """Create a termination message checker for the GroupChat."""
    def is_termination_msg(msg: dict[str, Any]) -> bool:
        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            return False
        content_upper = content.upper()
        return (
            "EVALUATION PASSED" in content_upper
            or "TERMINATE" in content_upper
        )
    return is_termination_msg
