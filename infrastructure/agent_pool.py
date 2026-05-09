"""Agent template pool for legacy single-agent mode.

The multi-agent expert mode now runs on AG2 beta network agents and no longer
uses ConversableAgent template cloning. We keep this pool only for single mode
so repeated CLI/gateway sessions do not have to rebuild the assistant agent
and its registered tools every time.

Why not deepcopy?
    AG2 agents hold OpenAI client objects with _thread.RLock which can't be
    pickled/deepcopied.  Our clone approach reconstructs a fresh agent and
    copies only the shareable parts (function_map, llm_config tools, system
    message, description).

Thread safety:
    All templates are created once at startup and never mutated afterwards.
    Each clone produces a fully independent agent (new defaultdict instances,
    fresh reply counters, etc.).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from autogen import ConversableAgent

from config.config import HarnessConfig, LlmConfig
from infrastructure.mcp.manager import McpManager
from infrastructure.skills.registry import SkillRegistry
from agents.factory import (
    create_single_agent,
    _register_context_transforms,
)

logger = logging.getLogger(__name__)


def _patch_autocompact_agent_ref(hook: Any, clone: ConversableAgent) -> None:
    """Walk into TransformMessages hooks and patch AutoCompactTransform._agent.

    TransformMessages wraps a list of MessageTransform objects.  If any of
    them is an AutoCompactTransform, its ``_agent`` attribute (set at init)
    points to the template.  We repoint it to the clone so that LLM calls
    for summarisation use the clone's client/context.
    """
    # hook is a bound method like TransformMessages._transform_messages
    tm = getattr(hook, "__self__", None)
    if tm is None:
        return
    transforms = getattr(tm, "_transforms", [])
    for transform in transforms:
        # Check for AutoCompactTransform by attribute rather than import
        # (avoids circular import and works if the class isn't loaded)
        if hasattr(transform, "_agent") and hasattr(transform, "_max_tokens"):
            transform._agent = clone


def _clone_agent(template: ConversableAgent) -> ConversableAgent:
    """Clone a template agent into a fresh, independent instance.

    What is shared (intentionally):
      - Function closures in _function_map (they capture McpManager which is
        stateless / connection-pooled — safe to share across sessions).
      - Tool schemas in llm_config (read-only after registration).

    What is reset (per-session):
      - _oai_messages (chat_messages) → empty defaultdict
      - _consecutive_auto_reply_counter → empty defaultdict
      - _human_input → empty list
      - reply_at_receive → empty defaultdict

    What is copied (reference, safe because hooks are stateless callables):
      - hook_lists → shallow copy of hook lists (context transforms, etc.)
    """
    clone = ConversableAgent(
        name=template._name,
        system_message=template.system_message,
        description=template._description,
        llm_config=template.llm_config,
        human_input_mode=template.human_input_mode,
    )

    # Copy function implementations (closures over McpManager — safe to share)
    for fname, fn in template._function_map.items():
        clone._function_map[fname] = fn

    # Copy hook lists (context transforms like Snip, AutoCompact are registered
    # as hooks).  Shallow copy is safe — the hook objects themselves are stateless
    # per-call (they read from the message list passed as argument).
    for hook_name, hooks in template.hook_lists.items():
        clone.hook_lists[hook_name] = list(hooks)

    # Patch AutoCompactTransform._agent references inside TransformMessages hooks
    # to point to the clone instead of the template.  This is needed because
    # AutoCompactTransform stores a reference to the agent for LLM client access.
    # The template's LLM client would work, but pointing to the clone is cleaner.
    for hook in clone.hook_lists.get("process_all_messages_before_reply", []):
        _patch_autocompact_agent_ref(hook, clone)

    # Ensure chat state is completely fresh
    clone._oai_messages = defaultdict(list)
    clone._consecutive_auto_reply_counter = defaultdict(int)
    clone._human_input = []
    clone.reply_at_receive = defaultdict(bool)

    return clone


class AgentPool:
    """Pre-created agent templates, cloned on demand per session.

    Usage::

        pool = AgentPool(llm_config, mcp_manager, skill_registry, harness_config)
        pool.initialize()          # creates & registers all templates

        # On each incoming message:
        agents = pool.acquire_single_agents()
    """

    def __init__(
        self,
        llm_config: LlmConfig,
        mcp_manager: McpManager,
        skill_registry: SkillRegistry | None = None,
        harness_config: HarnessConfig | None = None,
    ) -> None:
        self._llm_config = llm_config
        self._mcp_manager = mcp_manager
        self._skill_registry = skill_registry
        self._harness_config = harness_config

        # Template agents — populated by initialize(), never mutated after
        self._single_templates: dict[str, ConversableAgent] = {}
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Create template agents with all tools & skills registered.

        Called once at startup.  This is the "expensive" part — MCP tool
        registration, skill injection, context transform setup, etc.
        """
        if self._initialized:
            return

        logger.info("Initializing agent pool — creating templates...")

        # --- Single mode template ---
        self._single_templates = {
            "assistant": create_single_agent(
                self._llm_config, self._mcp_manager, self._skill_registry, self._harness_config,
            ),
        }

        if self._harness_config and self._harness_config.context.enabled:
            _register_context_transforms(
                self._single_templates["assistant"], self._harness_config.context,
            )

        self._initialized = True
        self._log_template_summary()

    def acquire_single_agents(self) -> dict[str, ConversableAgent]:
        """Clone single-mode templates into independent session agents."""
        self._ensure_initialized()
        agents = {}
        for key, template in self._single_templates.items():
            agents[key] = _clone_agent(template)
            logger.debug("Cloned single agent '%s' from template", key)
        return agents

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "AgentPool not initialized — call initialize() first"
            )

    def _log_template_summary(self) -> None:
        """Log what was registered for debugging."""
        for key, agent in self._single_templates.items():
            func_count = len(agent._function_map)
            tools_in_config = len(agent.llm_config.get("tools", []))
            logger.info(
                "  [single] template '%s': %d functions, %d tool schemas",
                key, func_count, tools_in_config,
            )
