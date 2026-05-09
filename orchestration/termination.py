from __future__ import annotations

from typing import Any, Callable


def create_termination_check() -> Callable[[dict[str, Any]], bool]:
    """Only explicit Evaluator completion/termination messages end the legacy flow."""
    def is_termination_msg(msg: dict[str, Any]) -> bool:
        content = msg.get("content", "")
        name = msg.get("name", "")

        if not content or not isinstance(content, str):
            return False

        content_upper = content.upper()

        if name == "Evaluator" and "TERMINATE" in content_upper:
            return True

        if name == "Evaluator" and "EVALUATION PASSED" in content_upper:
            return True

        return False

    return is_termination_msg
