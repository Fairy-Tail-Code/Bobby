from __future__ import annotations

from datetime import datetime
from pathlib import Path


_SNAPSHOT_GLOB = "snapshot_*.json"
_SNAPSHOT_DIR_FORMAT = "%Y-%m-%d %H-%M-%S"


def build_snapshot_path(
    session_root: str | Path,
    session_id: str,
    *,
    timestamp: datetime | None = None,
) -> Path:
    """Return the canonical snapshot path under one timestamped directory."""
    created_at = timestamp or datetime.now()
    root = Path(session_root)
    return root / created_at.strftime(_SNAPSHOT_DIR_FORMAT) / f"snapshot_{session_id}.json"


def iter_snapshot_paths(session_root: str | Path) -> list[Path]:
    """Return every snapshot file under the session root, including legacy root files."""
    root = Path(session_root)
    if not root.exists():
        return []
    return sorted(root.rglob(_SNAPSHOT_GLOB), reverse=True)


def find_snapshot_path(session_root: str | Path, session_id: str) -> Path | None:
    """Return the newest matching snapshot file for one session id, if any."""
    root = Path(session_root)
    if not root.exists():
        return None

    matches = sorted(root.rglob(f"snapshot_{session_id}.json"), reverse=True)
    if not matches:
        return None
    return matches[0]
