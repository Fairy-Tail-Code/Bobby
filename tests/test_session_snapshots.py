from __future__ import annotations

import json
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from infrastructure.session.session_snapshots import (
    build_snapshot_path,
    find_snapshot_path,
    iter_snapshot_paths,
)


def _write_snapshot(path: Path, *, session_id: str, timestamp: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "timestamp": timestamp,
                "prompt": "demo",
                "messages": [{"role": "user", "content": "hi"}],
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )


@contextmanager
def _workspace_temp_dir() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-session-snapshots"
    temp_dir = temp_root / uuid.uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_build_snapshot_path_uses_timestamp_subdirectory() -> None:
    with _workspace_temp_dir() as session_root:
        created_at = datetime(2026, 4, 28, 18, 30, 45)

        path = build_snapshot_path(session_root, "deadbeef", timestamp=created_at)

        assert path == session_root / "2026-04-28 18-30-45" / "snapshot_deadbeef.json"


def test_find_snapshot_path_locates_snapshot_in_timestamp_subdirectory() -> None:
    with _workspace_temp_dir() as session_root:
        snapshot_path = session_root / "2026-04-28 18-30-45" / "snapshot_deadbeef.json"
        _write_snapshot(
            snapshot_path,
            session_id="deadbeef",
            timestamp="2026-04-28T18:30:45",
        )

        assert find_snapshot_path(session_root, "deadbeef") == snapshot_path


def test_iter_snapshot_paths_discovers_root_and_nested_snapshots() -> None:
    with _workspace_temp_dir() as session_root:
        root_snapshot = session_root / "snapshot_root000.json"
        nested_snapshot = session_root / "2026-04-28 18-30-45" / "snapshot_nested0.json"
        _write_snapshot(
            root_snapshot,
            session_id="root0000",
            timestamp="2026-04-20T10:00:00",
        )
        _write_snapshot(
            nested_snapshot,
            session_id="nested000",
            timestamp="2026-04-28T18:30:45",
        )

        paths = iter_snapshot_paths(session_root)

        assert root_snapshot in paths
        assert nested_snapshot in paths
