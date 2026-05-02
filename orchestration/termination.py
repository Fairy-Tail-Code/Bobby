from __future__ import annotations

from typing import Any, Callable


def create_termination_check() -> Callable[[dict[str, Any]], bool]:
    """允许任何 agent 在用户明确要求取消时终止流程。"""
    def is_termination_msg(msg: dict[str, Any]) -> bool:
        content = msg.get("content", "")
        name = msg.get("name", "")

        if not content or not isinstance(content, str):
            return False

        content_upper = content.upper()

        if "TERMINATE" in content_upper:
            return True

        # Evaluator 审核通过也触发终止
        if name == "Evaluator" and "EVALUATION PASSED" in content_upper:
            return True

        return False

    return is_termination_msg