"""Cron configuration loading."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from utils.paths import get_home


@dataclass
class CronConfig:
    """Configuration for the Agent Cron MCP server."""
    enabled: bool = True
    storage_path: str = ""
    task_timeout: int = 3600

    def __post_init__(self) -> None:
        if not self.storage_path:
            home = get_home()
            self.storage_path = str(home / "cron_tasks.json")


def load_cron_config() -> CronConfig:
    """Load cron configuration from defaults or config file."""
    from utils.paths import get_config_dir

    config_dir = get_config_dir()
    cron_yaml = config_dir / "cron.yaml"

    if cron_yaml.exists():
        from config.config import _load_yaml
        data = _load_yaml(cron_yaml)
        return CronConfig(
            enabled=data.get("enabled", True),
            storage_path=data.get("storage_path", ""),
            task_timeout=data.get("task_timeout", 3600),
        )

    return CronConfig()
