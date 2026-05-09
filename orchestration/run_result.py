from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OrchestrationRunResult:
    transcript: list[dict[str, Any]]
    last_speaker: str
    status: str
