from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"

    @classmethod
    def coerce(cls, value: str) -> "MemoryType":
        normalized = (value or "").strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        allowed = ", ".join(item.value for item in cls)
        raise ValueError(f"Unsupported memory_type '{value}'. Allowed values: {allowed}")


@dataclass(slots=True)
class MemoryRecord:
    name: str
    title: str
    description: str
    memory_type: MemoryType
    path: Path


@dataclass(slots=True)
class MemoryDocument:
    record: MemoryRecord
    body: str
    raw_text: str
