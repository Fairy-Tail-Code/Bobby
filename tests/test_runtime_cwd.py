from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from infrastructure.mcp_servers.database_server import _resolve_root as resolve_database_root
from infrastructure.mcp_servers.shell_server import _resolve_cwd as resolve_shell_cwd
from infrastructure.mcp_servers.workspace_server import _resolve_root as resolve_workspace_root
from utils.paths import get_workspace_dir


@contextmanager
def _workspace_temp_home() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-runtime-cwd"
    home_dir = temp_root / uuid.uuid4().hex
    home_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield home_dir
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)


def test_default_mcp_roots_use_openharness_workspace(monkeypatch) -> None:
    with _workspace_temp_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))

        expected_workspace = get_workspace_dir().resolve(strict=False)

        assert resolve_workspace_root(None) == expected_workspace
        assert resolve_database_root(None) == expected_workspace
        assert Path(resolve_shell_cwd(None)) == expected_workspace
