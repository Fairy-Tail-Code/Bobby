from __future__ import annotations

import subprocess
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from click.testing import CliRunner

import cli as cli_module
from config.config import ConfigError


@contextmanager
def _temp_cli_dir() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-cli-server"
    root = temp_root / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_server_start_runs_foreground_by_default(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_server_main():
        return "server-main"

    def fake_asyncio_run(coro):
        called["coro"] = coro

    monkeypatch.setattr(cli_module, "_server_main", fake_server_main)
    monkeypatch.setattr(cli_module.asyncio, "run", fake_asyncio_run)

    result = CliRunner().invoke(cli_module.cli, ["server", "start"])

    assert result.exit_code == 0
    assert called["coro"] == "server-main"


def test_server_start_background_uses_background_launcher(monkeypatch) -> None:
    called = {"background": False}

    def fake_background() -> None:
        called["background"] = True

    monkeypatch.setattr(cli_module, "_server_start_background", fake_background)

    result = CliRunner().invoke(cli_module.cli, ["server", "start", "--background"])

    assert result.exit_code == 0
    assert called["background"] is True


def test_server_start_surfaces_config_error_cleanly(monkeypatch) -> None:
    async def fake_server_main():
        raise ConfigError("missing env config")

    monkeypatch.setattr(cli_module, "_server_main", fake_server_main)

    result = CliRunner().invoke(cli_module.cli, ["server", "start"])

    assert result.exit_code != 0
    assert "missing env config" in result.output
    assert "Traceback" not in result.output


def test_server_stop_removes_stale_pid_when_process_is_not_running(
    monkeypatch,
) -> None:
    with _temp_cli_dir() as root:
        pid_path = root / ".server.pid"
        pid_path.write_text("12880", encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_server_pid_path", lambda: pid_path)

        def fake_terminate(_pid: int) -> None:
            raise OSError(11, "stale pid")

        monkeypatch.setattr(cli_module, "_terminate_background_process", fake_terminate)

        result = CliRunner().invoke(cli_module.cli, ["server", "stop"])

        assert result.exit_code == 0
        assert "stale PID file removed" in result.output
        assert not pid_path.exists()


def test_server_stop_removes_invalid_pid_file(monkeypatch) -> None:
    with _temp_cli_dir() as root:
        pid_path = root / ".server.pid"
        pid_path.write_text("not-a-pid", encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_server_pid_path", lambda: pid_path)

        result = CliRunner().invoke(cli_module.cli, ["server", "stop"])

        assert result.exit_code == 0
        assert "stale PID file removed" in result.output
        assert not pid_path.exists()


def test_server_stop_removes_stale_pid_on_windows_taskkill_failure(
    monkeypatch,
) -> None:
    with _temp_cli_dir() as root:
        pid_path = root / ".server.pid"
        pid_path.write_text("12880", encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_server_pid_path", lambda: pid_path)

        error = subprocess.CalledProcessError(
            returncode=128,
            cmd=["taskkill", "/PID", "12880", "/F"],
            stderr="ERROR: Access denied",
        )

        def fake_terminate(_pid: int) -> None:
            raise error

        monkeypatch.setattr(cli_module, "_terminate_background_process", fake_terminate)

        result = CliRunner().invoke(cli_module.cli, ["server", "stop"])

        assert result.exit_code == 0
        assert "stale PID file removed" in result.output
        assert not pid_path.exists()


def test_server_start_background_clears_stale_pid_before_spawning(
    monkeypatch,
) -> None:
    with _temp_cli_dir() as root:
        pid_path = root / ".server.pid"
        pid_path.write_text("12880", encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_server_pid_path", lambda: pid_path)
        monkeypatch.setattr(cli_module, "_is_pid_running", lambda _pid: False)

        fake_proc = type("FakeProc", (), {"pid": 43210, "poll": lambda self: None})()

        def fake_popen(*_args, **_kwargs):
            return fake_proc

        monkeypatch.setattr(cli_module.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(cli_module, "_build_server_background_command", lambda: ["python", "cli.py"])
        monkeypatch.setattr(cli_module, "_open_background_server_log", lambda: None)

        result = CliRunner().invoke(cli_module.cli, ["server", "start", "--background"])

        assert result.exit_code == 0
        assert pid_path.read_text(encoding="utf-8").strip() == "43210"
        assert "Service started in background" in result.output
