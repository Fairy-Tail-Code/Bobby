from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextStrategy(ABC):
    """Base interface for context management strategies."""

    @abstractmethod
    def apply(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process the message list and return the (potentially modified) messages."""
        ...