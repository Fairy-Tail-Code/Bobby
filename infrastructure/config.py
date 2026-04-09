from __future__ import annotations

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
class HarnessConfig:
    max_rounds: int = 15
    score_threshold: int = 7
    dimensions: list[EvaluationDimension] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    context_strategy: str = "compaction"


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_llm_config(config_dir: Path) -> LlmConfig:
    raw = _load_yaml(config_dir / "llm.yaml")["llm"]
    return LlmConfig(
        planner=LlmAgentConfig(**raw["planner"]),
        generator=LlmAgentConfig(**raw["generator"]),
        evaluator=LlmAgentConfig(**raw["evaluator"]),
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
    return HarnessConfig(
        max_rounds=eval_cfg["max_rounds"],
        score_threshold=eval_cfg["score_threshold"],
        dimensions=dimensions,
        tech_stack=raw.get("tech_stack", {}),
        context_strategy=raw.get("context", {}).get("strategy", "compaction"),
    )