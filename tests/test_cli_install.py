from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from click.testing import CliRunner

from cli import cli


@contextmanager
def _temp_openharness_home() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-cli-install"
    home_dir = temp_root / uuid.uuid4().hex
    home_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield home_dir
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)


def test_install_keeps_env_template_out_of_config_dir(monkeypatch) -> None:
    with _temp_openharness_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))

        result = CliRunner().invoke(cli, ["install"])

        assert result.exit_code == 0
        assert (home_dir / "config" / "harness.yaml").exists()
        assert (home_dir / "config" / "mcp.yaml").exists()
        assert (home_dir / "config" / "skill.yaml").exists()
        assert not (home_dir / "config" / ".env.example").exists()
        assert (home_dir / ".env.example").exists()
        assert (home_dir / ".env").exists()
