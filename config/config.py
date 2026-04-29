from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from infrastructure.paths import get_home, get_config_dir, get_env_path


class ConfigError(ValueError):
    """Raised when required OpenHarness configuration is missing or invalid."""


@dataclass
class LlmAgentConfig:
    model: str
    base_url: str
    api_key: str
    temperature: float = 0.7

    def to_llm_config(self) -> dict[str, Any]:
        return {
            "config_list": [{
                "model": self.model,
                "base_url": self.base_url,
                "api_key": self.api_key,
            }],
            "temperature": self.temperature,
        }


@dataclass
class LlmConfig:
    pm: LlmAgentConfig
    planner: LlmAgentConfig
    generator: LlmAgentConfig
    evaluator: LlmAgentConfig


@dataclass
class McpServerConfig:
    name: str
    transport: str
    command: str
    args: list[str] = field(default_factory=list)
    startup_timeout: int = 30

@dataclass
class McpBaseConfig:
    tool_timeout: int


@dataclass
class McpConfig:
    servers: list[McpServerConfig]
    base_config: McpBaseConfig


@dataclass
class EvaluationDimension:
    name: str
    weight: str
    threshold: int


@dataclass
class ContextConfig:
    """Configuration for the context compression pipeline."""
    enabled: bool = True
    # Level 1 — Snip Compact
    max_messages: int = 60
    keep_first_message: bool = True
    # Level 4 — Auto Compact
    max_tokens: int = 80_000
    auto_compact_enabled: bool = True


@dataclass
class SmtpConfig:
    host: str
    port: int = 587
    user: str = ""
    password: str = ""
    use_tls: bool = True


@dataclass
class ImapConfig:
    host: str
    port: int = 993
    user: str = ""
    password: str = ""
    use_ssl: bool = True


@dataclass
class DingTalkConfig:
    client_id: str = ""      # AppKey / ClientId
    client_secret: str = ""  # AppSecret / ClientSecret
    robot_code: str = ""     # Robot code (usually same as client_id)


@dataclass
class FeishuConfig:
    app_id: str = ""
    app_secret: str = ""


@dataclass
class HitlConfig:
    mode: str = "stdin"  # "stdin" | "email" | "dingtalk" | "feishu"
    polling_interval: int = 30  # seconds between polls
    timeout: int = 3600  # max seconds to wait for a reply
    subject_prefix: str = "[OpenHarness]"


@dataclass
class ClaudeCodeConfig:
    """Configuration for claude -p based coding delegation."""
    model: str = ""              # Claude model alias (sonnet, opus, etc.)
    default_timeout: int = 600   # 单次任务超时（秒）
    max_retries: int = 2         # 失败后最大重试次数


@dataclass
class KnowledgeConfig:
    enabled: bool = False
    server_url: str = "http://localhost:8900"
    api_key: str = ""
    client_id: str = ""
    sync_interval_seconds: int = 300
    batch_size: int = 50
    max_retries: int = 3
    offline_enabled: bool = True
    pull_enabled: bool = True
    pull_categories: list[str] = field(default_factory=list)
    local_store_path: str = "knowledge_queue.db"
    collected_dir: str = "collected"


@dataclass
class HarnessConfig:
    mode: str = "swarm"  # "swarm" | "single"
    max_rounds: int = 15
    score_threshold: int = 7
    dimensions: list[EvaluationDimension] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    context: ContextConfig = field(default_factory=ContextConfig)
    hitl: HitlConfig = field(default_factory=HitlConfig)
    acpx: ClaudeCodeConfig = field(default_factory=ClaudeCodeConfig)
    knowledge: KnowledgeConfig = field(default_factory=KnowledgeConfig)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Missing required config file: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_dotenv(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict. Ignores comments and blank lines."""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _load_agent_env_config(env: dict[str, str], prefix: str) -> LlmAgentConfig:
    """Load an agent's LLM config from env vars with the given prefix."""
    missing = [f"{prefix}_{suffix}" for suffix in ("MODEL", "BASE_URL", "API_KEY") if not env.get(f"{prefix}_{suffix}")]
    if missing:
        env_path = get_env_path()
        missing_list = ", ".join(missing)
        raise ConfigError(
            f"Missing required LLM config in {env_path}: {missing_list}. "
            f"Edit {env_path} and fill the values from {env_path.with_name('.env.example')}."
        )
    return LlmAgentConfig(
        model=env[f"{prefix}_MODEL"],
        base_url=env[f"{prefix}_BASE_URL"],
        api_key=env[f"{prefix}_API_KEY"],
        temperature=float(env.get(f"{prefix}_TEMPERATURE", "0.7")),
    )


def load_llm_config() -> LlmConfig:
    """Load LLM config from .env file."""
    env = _load_dotenv(get_env_path())
    required_prefixes = ("PM", "PLANNER", "GENERATOR", "EVALUATOR")
    missing_keys: list[str] = []
    for prefix in required_prefixes:
        for suffix in ("MODEL", "BASE_URL", "API_KEY"):
            key = f"{prefix}_{suffix}"
            if not env.get(key):
                missing_keys.append(key)
    if missing_keys:
        env_path = get_env_path()
        missing_list = ", ".join(missing_keys)
        raise ConfigError(
            f"Missing required LLM config in {env_path}: {missing_list}. "
            f"Edit {env_path} and fill the values from {env_path.with_name('.env.example')}."
        )
    return LlmConfig(
        pm=_load_agent_env_config(env, "PM"),
        planner=_load_agent_env_config(env, "PLANNER"),
        generator=_load_agent_env_config(env, "GENERATOR"),
        evaluator=_load_agent_env_config(env, "EVALUATOR"),
    )

def load_mcp_config() -> McpConfig:
    mcp_yaml = _load_yaml(get_config_dir() / "mcp.yaml")
    mcp_servers = mcp_yaml["mcp_servers"]
    base_config = mcp_yaml["base_config"]
    servers = []
    for name, cfg in mcp_servers.items():
        servers.append(McpServerConfig(name=name, **cfg))
    return McpConfig(servers=servers, base_config=base_config)


def load_harness_config() -> HarnessConfig:
    raw = _load_yaml(get_config_dir() / "harness.yaml")["harness"]
    eval_cfg = raw["evaluation"]
    dimensions = [EvaluationDimension(**d) for d in eval_cfg["dimensions"]]
    ctx_raw = raw.get("context", {})
    context = ContextConfig(
        enabled=ctx_raw.get("enabled", True),
        max_messages=ctx_raw.get("max_messages", 60),
        keep_first_message=ctx_raw.get("keep_first_message", True),
        max_tokens=ctx_raw.get("max_tokens", 80_000),
        auto_compact_enabled=ctx_raw.get("auto_compact_enabled", True),
    )
    hitl_raw = raw.get("hitl", {})
    hitl = HitlConfig(
        mode=hitl_raw.get("mode", "stdin"),
        polling_interval=hitl_raw.get("polling_interval", 30),
        timeout=hitl_raw.get("timeout", 3600),
        subject_prefix=hitl_raw.get("subject_prefix", "[OpenHarness]"),
    )
    return HarnessConfig(
        mode=raw.get("mode", "swarm"),
        max_rounds=ctx_raw["max_rounds"],
        score_threshold=eval_cfg["score_threshold"],
        dimensions=dimensions,
        tech_stack=raw.get("tech_stack", {}),
        context=context,
        hitl=hitl,
        acpx=ClaudeCodeConfig(
            model=acpx_raw.get("model", ""),
            default_timeout=acpx_raw.get("default_timeout", 600),
            max_retries=acpx_raw.get("max_retries", 2),
        ) if (acpx_raw := raw.get("acpx", {})) else ClaudeCodeConfig(),
        knowledge=load_knowledge_config(),
    )


def load_smtp_config() -> SmtpConfig:
    env = _load_dotenv(get_env_path())
    return SmtpConfig(
        host=env.get("SMTP_HOST", ""),
        port=int(env.get("SMTP_PORT", "587")),
        user=env.get("SMTP_USER", ""),
        password=env.get("SMTP_PASSWORD", ""),
        use_tls=env.get("SMTP_USE_TLS", "true").lower() == "true",
    )


def load_imap_config() -> ImapConfig:
    env = _load_dotenv(get_env_path())
    return ImapConfig(
        host=env.get("IMAP_HOST", ""),
        port=int(env.get("IMAP_PORT", "993")),
        user=env.get("IMAP_USER", ""),
        password=env.get("IMAP_PASSWORD", ""),
        use_ssl=env.get("IMAP_USE_SSL", "true").lower() == "true",
    )


def load_role_emails() -> dict[str, str]:
    env = _load_dotenv(get_env_path())
    return {
        "pm": env.get("HITL_PM_EMAIL", ""),
        "planner": env.get("HITL_PLANNER_EMAIL", ""),
        "generator": env.get("HITL_GENERATOR_EMAIL", ""),
        "evaluator": env.get("HITL_EVALUATOR_EMAIL", ""),
    }


def load_dingtalk_config() -> DingTalkConfig:
    env = _load_dotenv(get_env_path())
    return DingTalkConfig(
        client_id=env.get("DINGTALK_CLIENT_ID", ""),
        client_secret=env.get("DINGTALK_CLIENT_SECRET", ""),
        robot_code=env.get("DINGTALK_ROBOT_CODE", ""),
    )


def load_feishu_config() -> FeishuConfig:
    env = _load_dotenv(get_env_path())
    return FeishuConfig(
        app_id=env.get("FEISHU_APP_ID", ""),
        app_secret=env.get("FEISHU_APP_SECRET", ""),
    )


def load_role_dingtalk_ids() -> dict[str, str]:
    env = _load_dotenv(get_env_path())
    return {
        "pm": env.get("HITL_PM_DINGTALK_USER_ID", ""),
        "planner": env.get("HITL_PLANNER_DINGTALK_USER_ID", ""),
        "generator": env.get("HITL_GENERATOR_DINGTALK_USER_ID", ""),
        "evaluator": env.get("HITL_EVALUATOR_DINGTALK_USER_ID", ""),
    }


def load_role_feishu_open_ids() -> dict[str, str]:
    env = _load_dotenv(get_env_path())
    return {
        "pm": env.get("HITL_PM_FEISHU_OPEN_ID", ""),
        "planner": env.get("HITL_PLANNER_FEISHU_OPEN_ID", ""),
        "generator": env.get("HITL_GENERATOR_FEISHU_OPEN_ID", ""),
        "evaluator": env.get("HITL_EVALUATOR_FEISHU_OPEN_ID", ""),
    }


@dataclass
class SkillAssignmentConfig:
    skills: dict[str, list[str]]
    mcp_servers: dict[str, list[str]]


def load_skill_assignment_config() -> SkillAssignmentConfig:
    raw = _load_yaml(get_config_dir() / "skill.yaml")
    return SkillAssignmentConfig(
        skills=raw.get("skills", {}),
        mcp_servers=raw.get("mcp_servers", {}),
    )


def load_knowledge_config() -> KnowledgeConfig:
    """Load knowledge sharing config from .env and harness.yaml."""
    home = get_home()
    env = _load_dotenv(get_env_path())
    config_dir = get_config_dir()
    raw = {}
    if (config_dir / "harness.yaml").exists():
        harness_raw = _load_yaml(config_dir / "harness.yaml")
        raw = harness_raw.get("harness", {}).get("knowledge", {})
    return KnowledgeConfig(
        enabled=raw.get("enabled", False),
        server_url=env.get("KNOWLEDGE_SERVER_URL", raw.get("server_url", "http://localhost:8900")),
        api_key=env.get("KNOWLEDGE_SERVER_API_KEY", ""),
        client_id=env.get("KNOWLEDGE_CLIENT_ID", ""),
        sync_interval_seconds=raw.get("sync_interval_seconds", 300),
        batch_size=raw.get("batch_size", 50),
        max_retries=raw.get("max_retries", 3),
        offline_enabled=raw.get("offline_enabled", True),
        pull_enabled=raw.get("pull_enabled", True),
        pull_categories=raw.get("pull_categories", []),
        local_store_path=raw.get("local_store_path", str(home / "knowledge_queue.db")),
        collected_dir=raw.get("collected_dir", str(home / "collected")),
    )
