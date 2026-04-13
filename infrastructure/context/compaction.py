from __future__ import annotations

from typing import Any

from infrastructure.context.base import ContextStrategy


class CompactionStrategy(ContextStrategy):
    """Uses AG2's built-in message compaction.

    The actual compression is handled by AG2's ``TransformMessages`` hooks
    (Level 1: ``MessageHistoryLimiter``, Level 4: ``AutoCompactTransform``)
    which are registered on each agent via ``_register_context_transforms()``
    in ``agents/factory.py``.

    This class is kept for backwards-compatibility with the strategy interface
    but is no longer the active entry point.
    """

    def apply(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages
