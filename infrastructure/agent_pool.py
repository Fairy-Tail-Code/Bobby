"""Agent pool placeholder kept for SessionManager wiring stability.

The project now builds both `single` and `swarm` sessions on top of
`autogen.beta.Agent` at runtime, so the old ConversableAgent template cloning
path is no longer used. We keep this small shell to avoid changing all
bootstrap wiring in one step.
"""
from __future__ import annotations

import logging

from config.config import HarnessConfig, LlmConfig
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class AgentPool:
    """Compatibility shell for the former legacy single-agent template pool."""

    def __init__(
        self,
        llm_config: LlmConfig,
        mcp_manager: McpManager,
        skill_registry: SkillRegistry | None = None,
        harness_config: HarnessConfig | None = None,
    ) -> None:
        del llm_config, mcp_manager, skill_registry, harness_config
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        logger.info("Agent pool initialized (beta runtime path no longer uses legacy templates)")
