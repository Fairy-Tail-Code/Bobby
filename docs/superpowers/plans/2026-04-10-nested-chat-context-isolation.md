# Nested Chat Context Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate each agent's internal ReAct loop (tool calls, intermediate output) from the shared group chat, so other agents only see clean final summaries.

**Architecture:** Split each of the 3 agents into an outer agent (in the group chat, no tools) and an inner worker (has tools). Use AG2's `register_nested_chats` API to connect them. The outer agent forwards messages to its worker, the worker does all the work internally, and only the final response is exposed to the group chat.

**Tech Stack:** AG2 (autogen), `register_nested_chats`, ConversableAgent

---

### Task 1: Refactor `agents/factory.py` — add helper functions

**Files:**
- Modify: `agents/factory.py`

- [ ] **Step 1: Add imports and helpers at the top of factory.py**

Replace the existing imports from `agents.planner`, `agents.generator`, `agents.evaluator` with a direct import of `load_prompt`. Add three new helper functions: `_create_outer`, `_create_worker`, `_register_nested_chat`.

After the existing imports (lines 1-19), replace lines 13-15 (the `from agents.planner import ...` block) with:

```python
from agents.prompts.loader import load_prompt
```

Then add the following three functions **after** the `EVALUATOR_SKILLS` list (after line 48) and **before** the existing `_inject_skill_summaries` function:

```python
# ── Role → MCP servers / skills mapping ──────────────────────────
_ROLE_MCP = {
    "planner": PLANNER_MCP_SERVERS,
    "generator": GENERATOR_MCP_SERVERS,
    "evaluator": EVALUATOR_MCP_SERVERS,
}

_ROLE_SKILLS = {
    "planner": PLANNER_SKILLS,
    "generator": GENERATOR_SKILLS,
    "evaluator": EVALUATOR_SKILLS,
}


def _create_outer(role: str, llm_config: LlmConfig) -> ConversableAgent:
    """Create a thin outer agent for the group chat. No tools."""
    prompt = load_prompt(role)
    llm_cfg = getattr(llm_config, role).to_llm_config()
    return ConversableAgent(
        name=role.capitalize(),
        system_message=prompt,
        llm_config=llm_cfg,
        human_input_mode="NEVER",
    )


def _create_worker(
    role: str,
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> ConversableAgent:
    """Create an inner worker agent with MCP tools and skills."""
    prompt = load_prompt(role)
    llm_cfg = getattr(llm_config, role).to_llm_config()
    worker = ConversableAgent(
        name=f"{role.capitalize()}Worker",
        system_message=prompt,
        llm_config=llm_cfg,
        human_input_mode="NEVER",
    )
    register_tools_for_agent(worker, mcp_manager, _ROLE_MCP[role])
    if skill_registry:
        _inject_skill_summaries(worker, _ROLE_SKILLS[role], skill_registry)
        register_load_skill_tool(worker, skill_registry, _ROLE_SKILLS[role])
    return worker


def _register_nested_chat(
    outer: ConversableAgent,
    worker: ConversableAgent,
) -> None:
    """Register a nested chat so the outer agent delegates to its inner worker."""
    outer.register_nested_chats(
        chat_queue=[{
            "recipient": worker,
            "summary_method": "last_msg",
            "max_turns": 1,
        }],
        trigger=lambda sender: True,
    )
```

- [ ] **Step 2: Verify imports compile**

Run: `cd C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness && python -c "from agents.factory import _create_outer, _create_worker, _register_nested_chat; print('OK')"`
Expected: `OK`

---

### Task 2: Rewrite `create_all_agents()` to use outer/worker pattern

**Files:**
- Modify: `agents/factory.py`

- [ ] **Step 1: Replace `create_all_agents` and remove old wrapper functions**

Delete the three old wrapper functions `create_planner_agent`, `create_generator_agent`, `create_evaluator_agent` (they are replaced by `_create_worker`). Replace `create_all_agents` with the new version:

```python
def create_all_agents(
    llm_config: LlmConfig,
    mcp_manager: McpManager,
    skill_registry: SkillRegistry | None = None,
) -> dict[str, ConversableAgent]:
    """Create all agents with nested chat context isolation.

    Returns a dict of OUTER agents (for the group chat). Each outer agent
    delegates to an internal worker via register_nested_chats, keeping
    tool calls and intermediate ReAct output hidden from other agents.
    """
    # 1. Create inner workers (with MCP tools + skills)
    workers = {
        "planner": _create_worker("planner", llm_config, mcp_manager, skill_registry),
        "generator": _create_worker("generator", llm_config, mcp_manager, skill_registry),
        "evaluator": _create_worker("evaluator", llm_config, mcp_manager, skill_registry),
    }

    # 2. Create outer agents (no tools, participate in group chat)
    agents = {
        "planner": _create_outer("planner", llm_config),
        "generator": _create_outer("generator", llm_config),
        "evaluator": _create_outer("evaluator", llm_config),
    }

    # 3. Wire nested chats: outer → worker
    for role in agents:
        _register_nested_chat(agents[role], workers[role])

    # 4. Setup handoffs on outer agents (unchanged logic)
    setup_handoffs(agents)

    return agents
```

Note: `setup_handoffs`, `_inject_skill_summaries` remain unchanged.

- [ ] **Step 2: Verify the module loads**

Run: `cd C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness && python -c "from agents.factory import create_all_agents; print('OK')"`
Expected: `OK`

---

### Task 3: Update existing factory tests

**Files:**
- Modify: `tests/test_agent_factory.py`

- [ ] **Step 1: Add tests for the new outer/worker structure**

The existing tests (`test_create_planner`, `test_create_generator`, `test_create_evaluator`) test the individual agent creation functions in `agents/planner.py`, `agents/generator.py`, `agents/evaluator.py`. Those functions are unchanged, so those tests stay.

Add new tests that verify the nested chat factory structure. We mock `McpManager` because we don't need real MCP connections for unit tests.

Append the following to `tests/test_agent_factory.py`:

```python
from unittest.mock import MagicMock, patch
from agents.factory import create_all_agents, _create_outer, _create_worker


@pytest.fixture
def mock_mcp_manager():
    """McpManager that reports no tools (no real connections)."""
    mgr = MagicMock()
    mgr.get_tools_for_server.return_value = []
    return mgr


def test_create_outer_planner(llm_config):
    agent = _create_outer("planner", llm_config)
    assert agent.name == "Planner"
    assert "Planner" in agent.system_message


def test_create_outer_generator(llm_config):
    agent = _create_outer("generator", llm_config)
    assert agent.name == "Generator"


def test_create_outer_evaluator(llm_config):
    agent = _create_outer("evaluator", llm_config)
    assert agent.name == "Evaluator"


def test_create_worker_has_worker_name(llm_config, mock_mcp_manager):
    worker = _create_worker("generator", llm_config, mock_mcp_manager)
    assert worker.name == "GeneratorWorker"


def test_create_all_agents_returns_three(llm_config, mock_mcp_manager):
    agents = create_all_agents(llm_config, mock_mcp_manager)
    assert set(agents.keys()) == {"planner", "generator", "evaluator"}


def test_outer_agents_have_correct_names(llm_config, mock_mcp_manager):
    agents = create_all_agents(llm_config, mock_mcp_manager)
    assert agents["planner"].name == "Planner"
    assert agents["generator"].name == "Generator"
    assert agents["evaluator"].name == "Evaluator"


def test_outer_agents_have_handoffs(llm_config, mock_mcp_manager):
    agents = create_all_agents(llm_config, mock_mcp_manager)
    for role, agent in agents.items():
        assert agent.handoffs is not None, f"{role} missing handoffs"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness && python -m pytest tests/test_agent_factory.py -v`
Expected: All tests PASS (both old and new)

---

### Task 4: Verify orchestration still works with outer agents

**Files:**
- No changes to `orchestration/group.py` or `main.py` — they already pass `agents_dict` to `arun_swarm`, which only sees outer agents.

- [ ] **Step 1: Run orchestration tests**

Run: `cd C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness && python -m pytest tests/test_orchestration.py -v`
Expected: All tests PASS (termination logic is unchanged)

- [ ] **Step 2: Run the full test suite**

Run: `cd C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add agents/factory.py tests/test_agent_factory.py docs/superpowers/specs/2026-04-10-nested-chat-context-isolation-design.md docs/superpowers/plans/2026-04-10-nested-chat-context-isolation.md
git commit -m "feat: nested chat context isolation — outer/worker agent split"
```

---

### Task 5: Manual smoke test

**Files:**
- No changes — just running the harness.

- [ ] **Step 1: Run the harness with a simple prompt**

Make sure MCP servers are configured (`.env` and `config/mcp.yaml` are set up).

Run: `cd C:\Users\WUJIEAI\PycharmProjects\OpenHarness\AG2_openharness && python main.py "Build a login system"`

**What to verify:**
1. Planner produces a spec → outer Planner's response in group chat is a clean summary (no tool call noise)
2. Generator builds the app → outer Generator's response is a clean summary like "Done! Running at localhost:8080. TRANSFER TO EVALUATOR" (no intermediate tool output visible)
3. Evaluator tests the app → response is an evaluation report with scores
4. The handoff between agents works (no infinite loop on "Stay")
5. If evaluation passes, the workflow terminates

**If `max_turns=1` causes the worker to produce incomplete results** (worker stops before finishing), increase `max_turns` to 5 in `_register_nested_chat` and retry.

---

## Self-Review

1. **Spec coverage**: All sections covered — outer/worker split, nested chat registration, handoff compatibility, no changes to other files.
2. **Placeholder scan**: No TBD/TODO. All code blocks are complete.
3. **Type consistency**: `_create_outer` returns `ConversableAgent`, `_create_worker` returns `ConversableAgent`, `create_all_agents` returns `dict[str, ConversableAgent]` — matches current usage in `main.py`.
4. **Backwards compatibility**: `agents/planner.py`, `agents/generator.py`, `agents/evaluator.py` are unchanged. Existing tests for those files still pass. Only `factory.py` is refactored.
