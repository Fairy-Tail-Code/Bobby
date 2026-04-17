from __future__ import annotations

from typing import Any, Callable
from typing import Any, Callable


def create_termination_check() -> Callable[[dict[str, Any]], bool]:
    """只允许 Evaluator 审核通过时终止流程。"""
    def is_termination_msg(msg: dict[str, Any]) -> bool:
        content = msg.get("content", "")
        name = msg.get("name", "")

        if not content or not isinstance(content, str):
            return False

        content_upper = content.upper()

        # 只有 Evaluator 才能触发终止
        if name == "Evaluator":
            return (
                "EVALUATION PASSED" in content_upper
                or "TERMINATE" in content_upper
            )

        return False

    return is_termination_msg


# todo 添加中止当前ReAct的能力