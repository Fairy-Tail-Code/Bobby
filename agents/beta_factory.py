from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlparse

from autogen.beta import Agent, PromptedSchema
from autogen.beta.config import OpenAIConfig
from autogen.beta.config.config import ModelConfig
from autogen.beta.middleware.builtin.history_limiter import HistoryLimiter
from autogen.beta.middleware.builtin.token_limiter import TokenLimiter
from autogen.beta.tools.final.function_tool import FunctionTool

from agents.network_models import NetworkNextStep, NetworkTurn
from agents.prompts.loader import load_prompt
from config.config import ContextConfig, HarnessConfig, LlmAgentConfig, LlmConfig, SkillAssignmentConfig, load_skill_assignment_config
from infrastructure.mcp.beta_tool_bridge import build_beta_tools_for_servers
from infrastructure.mcp.manager import McpManager
from infrastructure.llm.deepseek_beta_config import DeepSeekOpenAIConfig
from infrastructure.memory.beta_tool import build_beta_memory_tools
from infrastructure.memory.injection import build_memory_block
from infrastructure.skills.beta_tool import build_beta_skill_tools
from infrastructure.skills.registry import SkillRegistry

_skill_assignment: SkillAssignmentConfig | None = None


def _get_skill_assignment() -> SkillAssignmentConfig:
    global _skill_assignment
    if _skill_assignment is None:
        _skill_assignment = load_skill_assignment_config()
    return _skill_assignment


def _is_deepseek_backend(agent_config: LlmAgentConfig) -> bool:
    base_url = (agent_config.base_url or "").strip().lower()
    if not base_url:
        return False

    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = (parsed.netloc or parsed.path or base_url).lower()
    return "deepseek" in host or "deepseek" in base_url


def _to_beta_config(agent_config: LlmAgentConfig) -> ModelConfig:
    if _is_deepseek_backend(agent_config):
        return DeepSeekOpenAIConfig(
            model=agent_config.model,
            api_key=agent_config.api_key,
            base_url=agent_config.base_url,
            temperature=agent_config.temperature,
            streaming=agent_config.stream,
        )

    return OpenAIConfig(
        model=agent_config.model,
        api_key=agent_config.api_key,
        base_url=agent_config.base_url,
        temperature=agent_config.temperature,
        streaming=agent_config.stream,
    )


def _supports_native_response_schema(agent_config: LlmAgentConfig) -> bool:
    return not _is_deepseek_backend(agent_config)


def _build_network_contract(
    *,
    role_label: str,
    allowed_steps: Iterable[NetworkNextStep],
    native_response_schema: bool,
) -> str:
    step_list = ", ".join(step.value for step in allowed_steps)
    contract = (
        "## Beta Network Contract\n"
        "你当前运行在 AG2 beta network 风格的显式编排中。\n"
        "忽略旧 prompt 里所有关于 `transfer_to_*`、`terminate_command`、"
        "`handoff tool`、`swarm/group chat manager` 的历史说明；这些旧工具现在不存在。\n"
        f"你是 `{role_label}`，你的回复必须满足统一结构：\n"
        "- `message`: 当前这一步真正要说的话；如果你要提问，就把问题完整写在这里；如果你要交接，就把交接内容完整写在这里。\n"
        f"- `next_step`: 只能从以下值里选一个：{step_list}\n"
        "不要在 `message` 里写“调用 transfer tool”之类的描述。"
    )
    if native_response_schema:
        return contract + "\n系统会按 schema 校验你的最终回复，不要输出该结构之外的额外文字。"
    return (
        contract
        + "\n当前模型后端不支持原生 `response_format=json_schema`。"
        "系统会通过 prompt schema 约束你的结构化输出。"
        "你仍然必须只输出符合 schema 的 JSON，不要输出 `[PM]`、`[Planner]` 这类身份前缀，不要加额外解释。"
    )


def _build_response_schema(native_response_schema: bool):
    if native_response_schema:
        return NetworkTurn
    return PromptedSchema(NetworkTurn)


def _build_prompt(
    *,
    role_key: str,
    base_prompt_name: str,
    allowed_steps: Iterable[NetworkNextStep],
    native_response_schema: bool,
    harness_config: HarnessConfig | None,
    skill_registry: SkillRegistry | None,
) -> str:
    prompt_parts = [load_prompt(base_prompt_name)]
    prompt_parts.append(
        _build_network_contract(
            role_label=role_key,
            allowed_steps=allowed_steps,
            native_response_schema=native_response_schema,
        )
    )

    skill_assignment = _get_skill_assignment()
    if skill_registry:
        summary_block = skill_registry.build_summary_block(
            skill_assignment.skills.get(role_key, [])
        )
        if summary_block:
            prompt_parts.append(summary_block)

    if harness_config and harness_config.memory.enabled:
        prompt_parts.append(build_memory_block(harness_config.memory))

    return "\n\n".join(part.strip() for part in prompt_parts if part and part.strip())


def _build_role_tools(
    *,
    role_key: str,
    mcp_manager: McpManager | None,
    skill_registry: SkillRegistry | None,
    harness_config: HarnessConfig | None,
) -> list[FunctionTool]:
    skill_assignment = _get_skill_assignment()
    tools: list[FunctionTool] = []

    if mcp_manager:
        tools.extend(
            build_beta_tools_for_servers(
                mcp_manager,
                skill_assignment.mcp_servers.get(role_key, []),
            )
        )

    if skill_registry:
        tools.extend(
            build_beta_skill_tools(
                skill_registry,
                skill_assignment.skills.get(role_key, []),
            )
        )

    if harness_config and harness_config.memory.enabled:
        tools.extend(build_beta_memory_tools(harness_config.memory))

    return tools


def _build_middleware(context_config: ContextConfig | None) -> list:
    if not context_config or not context_config.enabled:
        return []
    middleware = [HistoryLimiter(context_config.max_messages)]
    if context_config.max_tokens > 0:
        middleware.append(TokenLimiter(context_config.max_tokens))
    return middleware


def _create_role_agent(
    *,
    role_key: str,
    display_name: str,
    base_prompt_name: str,
    llm_agent_config: LlmAgentConfig,
    allowed_steps: Iterable[NetworkNextStep],
    mcp_manager: McpManager | None,
    skill_registry: SkillRegistry | None,
    harness_config: HarnessConfig | None,
) -> Agent[Any]:
    native_response_schema = _supports_native_response_schema(llm_agent_config)
    return Agent(
        name=display_name,
        prompt=_build_prompt(
            role_key=role_key,
            base_prompt_name=base_prompt_name,
            allowed_steps=allowed_steps,
            native_response_schema=native_response_schema,
            harness_config=harness_config,
            skill_registry=skill_registry,
        ),
        config=_to_beta_config(llm_agent_config),
        tools=_build_role_tools(
            role_key=role_key,
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            harness_config=harness_config,
        ),
        middleware=_build_middleware(harness_config.context if harness_config else None),
        response_schema=_build_response_schema(native_response_schema),
    )


def create_swarm_network_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
    harness_config: HarnessConfig | None = None,
) -> dict[str, Agent[Any]]:
    return {
        "pm": _create_role_agent(
            role_key="pm",
            display_name="PM",
            base_prompt_name="pm",
            llm_agent_config=llm_config.pm,
            allowed_steps=[
                NetworkNextStep.ASK_USER,
                NetworkNextStep.HANDOFF_PLANNER,
                NetworkNextStep.TERMINATE,
            ],
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            harness_config=harness_config,
        ),
        "planner": _create_role_agent(
            role_key="planner",
            display_name="Planner",
            base_prompt_name="planner",
            llm_agent_config=llm_config.planner,
            allowed_steps=[
                NetworkNextStep.ASK_USER,
                NetworkNextStep.HANDOFF_GENERATOR,
                NetworkNextStep.HANDOFF_EVALUATOR,
                NetworkNextStep.TERMINATE,
            ],
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            harness_config=harness_config,
        ),
        "generator": _create_role_agent(
            role_key="generator",
            display_name="Generator",
            base_prompt_name="generator",
            llm_agent_config=llm_config.generator,
            allowed_steps=[
                NetworkNextStep.ASK_USER,
                NetworkNextStep.HANDOFF_PLANNER,
                NetworkNextStep.HANDOFF_EVALUATOR,
                NetworkNextStep.TERMINATE,
            ],
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            harness_config=harness_config,
        ),
        "evaluator": _create_role_agent(
            role_key="evaluator",
            display_name="Evaluator",
            base_prompt_name="evaluator",
            llm_agent_config=llm_config.evaluator,
            allowed_steps=[
                NetworkNextStep.ASK_USER,
                NetworkNextStep.HANDOFF_PLANNER,
                NetworkNextStep.HANDOFF_GENERATOR,
                NetworkNextStep.COMPLETE,
                NetworkNextStep.TERMINATE,
            ],
            mcp_manager=mcp_manager,
            skill_registry=skill_registry,
            harness_config=harness_config,
        ),
    }

