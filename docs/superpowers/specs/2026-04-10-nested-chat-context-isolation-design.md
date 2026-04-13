# Nested Chat Context Isolation Design

**Date**: 2026-04-10
**Status**: Draft

## Problem

Current 3-agent swarm (Planner → Generator → Evaluator) shares ALL messages in the group chat, including intermediate tool calls, shell output, debug logs, etc. When Generator works for an hour writing code, the Evaluator receives the entire history — hundreds of tool call messages that pollute its context and degrade its reasoning quality.

**Example of current behavior**:
```
GroupChat messages (shared by ALL agents):
  [1] Planner: "Spec for login system..."
  [2] Generator: "Creating project structure..."
  [3] Tool result: 200 lines of shell output
  [4] Generator: "Writing backend code..."
  [5] Tool result: 150 lines of file content
  [6] Generator: "Running tests..." + 500 lines of error logs
  [7] Generator: "Fixed bug..."
  [8] Generator: "Done! Running at localhost:8080. TRANSFER TO EVALUATOR"

→ Evaluator sees ALL of [1]-[8], including irrelevant tool output.
```

**Desired behavior**:
```
GroupChat messages (shared by ALL agents):
  [1] Planner: "Spec for login system..."
  [2] Generator: "Done! Login system running at localhost:8080. Features: register/login/logout. TRANSFER TO EVALUATOR"

→ Evaluator sees ONLY [1]-[2]. Clean context.
```

## Solution

Use AG2's `register_nested_chats` API. Each agent is split into an **outer agent** (in the group chat, no tools) and an **inner worker** (has tools, does the actual work). When the outer agent receives a message, it triggers an internal conversation with its worker. Only the worker's final response is exposed to the outer group chat.

```
Outer GroupChat (clean summaries only)
├── Planner (outer, no tools)
│   └── nested chat → PlannerWorker (inner, has tools) ← isolated
├── Generator (outer, no tools)
│   └── nested chat → GeneratorWorker (inner, has tools) ← isolated
└── Evaluator (outer, no tools)
    └── nested chat → EvaluatorWorker (inner, has tools) ← isolated
```

## Architecture

### Agent Split

| Outer Agent (group chat) | Inner Worker (nested) | Tools on |
|---|---|---|
| Planner | PlannerWorker | workspace, shell |
| Generator | GeneratorWorker | shell, git, workspace, browser, docker, database |
| Evaluator | EvaluatorWorker | browser, shell, http_api, workspace |

### How It Works

1. User sends prompt → Planner (outer) receives it
2. Planner triggers nested chat → PlannerWorker generates spec
3. PlannerWorker's final response becomes Planner's reply in group chat
4. Handoff mechanism sees "TRANSFER TO GENERATOR" → routes to Generator (outer)
5. Generator triggers nested chat → GeneratorWorker builds the app (tool calls stay internal)
6. GeneratorWorker's final response ("Done! Running at localhost:8080. TRANSFER TO EVALUATOR") becomes Generator's reply
7. Evaluator (outer) triggers nested chat → EvaluatorWorker tests the app
8. Continue until Evaluator says "EVALUATION PASSED" → TerminateTarget

### Message Flow Detail

```python
# Nested chat registration pattern
generator_outer.register_nested_chats(
    [{
        "recipient": generator_worker,
        "summary_method": "last_msg",
        "max_turns": 1,  # worker does full ReAct in one response
    }],
    trigger=lambda sender: True,
)
```

With `max_turns=1`:
- Outer agent forwards the outer chat message to the worker (no LLM call)
- Worker receives task, runs full ReAct loop (LLM + tools, all internal)
- Worker's final response is extracted via `summary_method="last_msg"`
- This response becomes the outer agent's reply in the group chat

**Zero extra LLM cost**: the outer agent doesn't call the LLM. Only the inner worker does.

### Why max_turns=1

AG2's ReAct loop runs **within a single `generate_reply` call**. The worker can make dozens of tool calls (create files, run commands, debug) in one response. The loop continues as long as the LLM generates tool calls. Only when the LLM produces a plain text response (e.g., "Done! TRANSFER TO EVALUATOR") does the ReAct loop end.

If a specific task requires the worker to produce intermediate text responses (not just tool calls), increase `max_turns`. Start with `max_turns=1`, increase only if needed.

### Handoff Compatibility

The outer agents still have `handoffs` configured with `OnCondition` + `StringLLMCondition`. The nested chat summary (worker's final response) contains the transfer phrase (e.g., "TRANSFER TO EVALUATOR"), so the handoff mechanism works unchanged.

## Implementation

### Changes to `agents/factory.py`

```python
def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> dict[str, ConversableAgent]:
    # 1. Create inner workers (with tools + skills)
    planner_worker = _create_worker("planner", llm_config, mcp_manager, skill_registry)
    generator_worker = _create_worker("generator", llm_config, mcp_manager, skill_registry)
    evaluator_worker = _create_worker("evaluator", llm_config, mcp_manager, skill_registry)

    # 2. Create outer agents (no tools, in group chat)
    agents = {
        "planner": _create_outer("planner", llm_config),
        "generator": _create_outer("generator", llm_config),
        "evaluator": _create_outer("evaluator", llm_config),
    }

    # 3. Register nested chats
    _register_nested(agents["planner"], planner_worker)
    _register_nested(agents["generator"], generator_worker)
    _register_nested(agents["evaluator"], evaluator_worker)

    # 4. Setup handoffs on outer agents
    setup_handoffs(agents)

    return agents


def _create_outer(role: str, llm_config: LlmConfig) -> ConversableAgent:
    """Create a thin outer agent for the group chat. No tools."""
    # Outer agent uses the SAME prompt as the worker — it needs to understand
    # the role to formulate the right delegation message.
    prompt = load_prompt(role)
    return ConversableAgent(
        name=role.capitalize(),  # Planner, Generator, Evaluator
        system_message=prompt,
        llm_config=_get_llm_config(llm_config, role),
        human_input_mode="NEVER",
    )


def _create_worker(
    role: str, llm_config: LlmConfig,
    mcp_manager: McpManager, skill_registry: SkillRegistry | None,
) -> ConversableAgent:
    """Create an inner worker agent with tools and skills."""
    prompt = load_prompt(role)
    worker = ConversableAgent(
        name=f"{role.capitalize()}Worker",
        system_message=prompt,
        llm_config=_get_llm_config(llm_config, role),
        human_input_mode="NEVER",
    )
    # Register MCP tools on worker
    server_map = {
        "planner": PLANNER_MCP_SERVERS,
        "generator": GENERATOR_MCP_SERVERS,
        "evaluator": EVALUATOR_MCP_SERVERS,
    }
    register_tools_for_agent(worker, mcp_manager, server_map[role])

    # Register skills on worker
    skill_map = {
        "planner": PLANNER_SKILLS,
        "generator": GENERATOR_SKILLS,
        "evaluator": EVALUATOR_SKILLS,
    }
    if skill_registry:
        _inject_skill_summaries(worker, skill_map[role], skill_registry)
        register_load_skill_tool(worker, skill_registry, skill_map[role])

    return worker


def _register_nested(outer: ConversableAgent, worker: ConversableAgent) -> None:
    """Register a nested chat: outer → worker."""
    outer.register_nested_chats(
        [{
            "recipient": worker,
            "summary_method": "last_msg",
            "max_turns": 1,
        }],
        trigger=lambda sender: True,
    )
```

### Changes to `orchestration/group.py`

No changes needed. The outer agents are passed to `arun_swarm` as before.

### Changes to `main.py`

No changes needed. `create_all_agents` returns the outer agents.

### Other Files

- `agents/planner.py`, `agents/generator.py`, `agents/evaluator.py`: No changes. The `create_*` functions are still used by `_create_worker`.
- `agents/prompts/*.md`: No changes. Same prompts used by workers.

## Configuration

| Agent | max_turns | Rationale |
|---|---|---|
| Planner | 1 | Text generation, minimal tool usage |
| Generator | 1 (tune to 5 if needed) | Full ReAct in one response; increase if LLM stops early |
| Evaluator | 1 (tune to 3 if needed) | Browser testing in one response |

Start with `max_turns=1` for all. If the worker produces a partial result (LLM generates non-tool text before completing), increase.

## Risks & Mitigations

### Risk 1: Worker can't complete in one ReAct session
**Mitigation**: Increase `max_turns`. With `max_turns=N` (N > 1), the outer agent generates follow-up messages to keep the worker going. This adds LLM cost but ensures completion.

### Risk 2: Worker's final response doesn't contain transfer phrase
**Mitigation**: The prompt already instructs agents to end with transfer phrases. The `after_work` fallback handles missing phrases (StayTarget for Generator/Planner, TerminateTarget for Evaluator).

### Risk 3: Outer agent loses context between nested chat invocations
**Mitigation**: Each nested chat receives the last message from the outer group chat. Since all agents use nested chats, the outer group chat only contains clean summaries — safe to pass as context. If more context is needed, customize the `message` function in the nested chat config.

### Risk 4: Double the agents means more memory/connections
**Mitigation**: Workers are lightweight ConversableAgent instances. MCP connections are shared through McpManager. No additional MCP server processes needed.

## Summary of Changes

| File | Change |
|---|---|
| `agents/factory.py` | Major refactor: split into outer/worker, register nested chats |
| `agents/planner.py` | No change |
| `agents/generator.py` | No change |
| `agents/evaluator.py` | No change |
| `agents/prompts/*.md` | No change |
| `orchestration/group.py` | No change |
| `main.py` | No change |
