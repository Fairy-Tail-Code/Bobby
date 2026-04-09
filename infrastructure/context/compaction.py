from __future__ import annotations

from typing import Any

from infrastructure.context.base import ContextStrategy


class CompactionStrategy(ContextStrategy):
    """Uses AG2's built-in message compaction.

    Currently a no-op since AG2 handles compaction internally.
    This exists as a placeholder for future customization.
    """

    def apply(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages