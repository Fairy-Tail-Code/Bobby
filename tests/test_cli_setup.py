from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

import yaml
from click.testing import CliRunner

import cli as cli_module


@contextmanager
def _temp_setup_home() -> Path:
    temp_root = Path(__file__).resolve().parent.parent / ".test-tmp-cli-setup"
    home_dir = temp_root / uuid.uuid4().hex
    (home_dir / "config").mkdir(parents=True, exist_ok=True)
    try:
        yield home_dir
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)


def test_setup_preserves_env_template_and_fills_complete_env(monkeypatch) -> None:
    with _temp_setup_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        defaults_env = (
            Path(__file__).resolve().parent.parent / "install" / "defaults" / ".env.example"
        ).read_text(encoding="utf-8")
        (home_dir / ".env.example").write_text(defaults_env, encoding="utf-8")
        (home_dir / "config" / "harness.yaml").write_text(
            """
harness:
  mode: swarm
  evaluation:
    score_threshold: 7
    dimensions: []
  context:
    enabled: true
    max_messages: 60
    keep_first_message: true
    max_tokens: 80000
    auto_compact_enabled: true
    max_rounds: 15
  hitl:
    mode: email
""".strip(),
            encoding="utf-8",
        )

        selections = {
            "llm_provider": "zhipu",
            "hitl_mode": "email",
        }
        confirms = {
            "reconfigure_env": True,
            "same_llm_config": True,
            "configure_gitee": True,
            "configure_feishu_service": True,
            "same_hitl_email": False,
        }
        values = {
            "shared_base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
            "shared_model": "GLM-5.1",
            "shared_api_key": "glm-key",
            "GITEE_ACCESS_TOKEN": "gitee-token",
            "GITEE_BASE_URL": "https://gitee.com/api/v5",
            "FEISHU_APP_ID": "cli_app_id",
            "FEISHU_APP_SECRET": "cli_app_secret",
            "SMTP_HOST": "smtp.qq.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "sender@example.com",
            "SMTP_PASSWORD": "smtp-secret",
            "IMAP_HOST": "imap.qq.com",
            "IMAP_PORT": "993",
            "IMAP_USER": "sender@example.com",
            "IMAP_PASSWORD": "imap-secret",
            "HITL_PM_EMAIL": "pm@example.com",
            "HITL_PLANNER_EMAIL": "planner@example.com",
            "HITL_GENERATOR_EMAIL": "generator@example.com",
            "HITL_EVALUATOR_EMAIL": "evaluator@example.com",
        }

        monkeypatch.setattr(
            cli_module,
            "_select_option",
            lambda name, _title, _options, default=None, description=None: selections.get(name, default),
        )
        monkeypatch.setattr(
            cli_module,
            "_confirm_choice",
            lambda name, _text, default=True: confirms.get(name, default),
        )
        monkeypatch.setattr(
            cli_module,
            "_prompt_value",
            lambda name, _label, default="", secret=False, allow_empty=False: values.get(name, default),
        )

        result = CliRunner().invoke(cli_module.cli, ["setup"])

        assert result.exit_code == 0
        env_text = (home_dir / ".env").read_text(encoding="utf-8")
        assert "PM_MODEL=GLM-5.1" in env_text
        assert "PLANNER_MODEL=GLM-5.1" in env_text
        assert "GENERATOR_API_KEY=glm-key" in env_text
        assert "EVALUATOR_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4" in env_text
        assert "GITEE_ACCESS_TOKEN=gitee-token" in env_text
        assert "FEISHU_APP_ID=cli_app_id" in env_text
        assert "SMTP_USER=sender@example.com" in env_text
        assert "IMAP_PASSWORD=imap-secret" in env_text
        assert "HITL_PM_EMAIL=pm@example.com" in env_text
        assert "HITL_EVALUATOR_EMAIL=evaluator@example.com" in env_text
        assert "DINGTALK_CLIENT_ID=" in env_text
        assert "HITL_PM_FEISHU_OPEN_ID=" in env_text


def test_setup_updates_harness_hitl_mode(monkeypatch) -> None:
    with _temp_setup_home() as home_dir:
        monkeypatch.setenv("OPENHARNESS_HOME", str(home_dir))
        (home_dir / ".env.example").write_text("PM_MODEL=\n", encoding="utf-8")
        (home_dir / "config" / "harness.yaml").write_text(
            """
harness:
  mode: swarm
  evaluation:
    score_threshold: 7
    dimensions: []
  context:
    enabled: true
    max_messages: 60
    keep_first_message: true
    max_tokens: 80000
    auto_compact_enabled: true
    max_rounds: 15
  hitl:
    mode: email
""".strip(),
            encoding="utf-8",
        )

        selections = {
            "llm_provider": "openai",
            "hitl_mode": "feishu",
        }
        confirms = {
            "same_llm_config": True,
            "configure_gitee": False,
            "configure_feishu_service": True,
            "same_hitl_feishu_open_id": True,
        }
        values = {
            "shared_base_url": "https://api.openai.com/v1",
            "shared_model": "gpt-4o",
            "shared_api_key": "openai-key",
            "FEISHU_APP_ID": "app-id",
            "FEISHU_APP_SECRET": "app-secret",
            "shared_hitl_feishu_open_id": "ou_123",
        }

        monkeypatch.setattr(
            cli_module,
            "_select_option",
            lambda name, _title, _options, default=None, description=None: selections.get(name, default),
        )
        monkeypatch.setattr(
            cli_module,
            "_confirm_choice",
            lambda name, _text, default=True: confirms.get(name, default),
        )
        monkeypatch.setattr(
            cli_module,
            "_prompt_value",
            lambda name, _label, default="", secret=False, allow_empty=False: values.get(name, default),
        )

        result = CliRunner().invoke(cli_module.cli, ["setup"])

        assert result.exit_code == 0
        harness_yaml = yaml.safe_load((home_dir / "config" / "harness.yaml").read_text(encoding="utf-8"))
        assert harness_yaml["harness"]["hitl"]["mode"] == "feishu"
        env_text = (home_dir / ".env").read_text(encoding="utf-8")
        assert "FEISHU_APP_ID=app-id" in env_text
        assert "HITL_PM_FEISHU_OPEN_ID=ou_123" in env_text
        assert "HITL_EVALUATOR_FEISHU_OPEN_ID=ou_123" in env_text


def test_install_scripts_delegate_to_harness_setup() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    install_sh = (repo_root / "install" / "install.sh").read_text(encoding="utf-8")
    install_ps1 = (repo_root / "install" / "install.ps1").read_text(encoding="utf-8")

    assert 'OPENHARNESS_HOME="$home" "$home/bin/harness" setup' in install_sh
    assert '& (Join-Path $HarnessHome "bin\\harness.exe") setup' in install_ps1
    assert 'falling back to built-in installer wizard' in install_ps1
