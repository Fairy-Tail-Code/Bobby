from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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
class McpConfig:
    servers: list[McpServerConfig]


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
class HarnessConfig:
    max_rounds: int = 15
    score_threshold: int = 7
    dimensions: list[EvaluationDimension] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    context: ContextConfig = field(default_factory=ContextConfig)


def _load_yaml(path: Path) -> dict:
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
    return LlmAgentConfig(
        model=env[f"{prefix}_MODEL"],
        base_url=env[f"{prefix}_BASE_URL"],
        api_key=env[f"{prefix}_API_KEY"],
        temperature=float(env.get(f"{prefix}_TEMPERATURE", "0.7")),
    )


def load_llm_config(project_dir: Path) -> LlmConfig:
    """Load LLM config from .env file in the project directory."""
    env = _load_dotenv(project_dir / ".env")
    return LlmConfig(
        planner=_load_agent_env_config(env, "PLANNER"),
        generator=_load_agent_env_config(env, "GENERATOR"),
        evaluator=_load_agent_env_config(env, "EVALUATOR"),
    )


def load_mcp_config(config_dir: Path) -> McpConfig:
    raw = _load_yaml(config_dir / "mcp.yaml")["mcp_servers"]
    servers = []
    for name, cfg in raw.items():
        servers.append(McpServerConfig(name=name, **cfg))
    return McpConfig(servers=servers)


def load_harness_config(config_dir: Path) -> HarnessConfig:
    raw = _load_yaml(config_dir / "harness.yaml")["harness"]
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
    return HarnessConfig(
        max_rounds=eval_cfg["max_rounds"],
        score_threshold=eval_cfg["score_threshold"],
        dimensions=dimensions,
        tech_stack=raw.get("tech_stack", {}),
        context=context,
    )