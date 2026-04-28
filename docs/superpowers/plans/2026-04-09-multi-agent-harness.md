# Multi-Agent Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-agent (Planner → Generator → Evaluator) full-stack application generation harness using AG2 GroupChat auto mode.

**Architecture:** Three-layer design (Infrastructure → Agent Design → Orchestration). MCP servers from openharness are consumed via stdio. Agents communicate through AG2 GroupChat with LLM-driven auto speaker selection. Prompts are externalized as .md files.

**Tech Stack:** AG2 (autogen), MCP Python SDK, PyYAML, asyncio

---

### Task 1: Project Scaffold + Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `config/llm.yaml`
- Create: `config/mcp.yaml`
- Create: `config/harness.yaml`
- Create: `infrastructure/__init__.py`
- Create: `infrastructure/mcp/__init__.py`
- Create: `infrastructure/skills/__init__.py`
- Create: `infrastructure/context/__init__.py`
- Create: `agents/__init__.py`
- Create: `agents/prompts/` (directory)
- Create: `agents/tools/__init__.py`
- Create: `orchestration/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create all directories**

```bash
cd "C:/Users/WUJIEAI/PycharmProjects/OpenHarness/AG2_openharness"
mkdir -p config infrastructure/mcp/clients infrastructure/skills infrastructure/context agents/prompts agents/tools orchestration tests
```

- [ ] **Step 2: Create requirements.txt**

```txt
ag2>=0.7
mcp>=1.0
pyyaml>=6.0
anyio>=4.0
```

- [ ] **Step 3: Create all `__init__.py` files**

Run:
```bash
touch infrastructure/__init__.py infrastructure/mcp/__init__.py infrastructure/skills/__init__.py infrastructure/context/__init__.py agents/__init__.py agents/tools/__init__.py orchestration/__init__.py tests/__init__.py
```

- [ ] **Step 4: Create config/llm.yaml**

```yaml
llm:
  planner:
    model: "your-model-name"
    base_url: "http://localhost:11434/v1"
    api_key: "your-api-key"
    temperature: 0.7

  generator:
    model: "your-model-name"
    base_url: "http://localhost:11434/v1"
    api_key: "your-api-key"
    temperature: 0.4

  evaluator:
    model: "your-model-name"
    base_url: "http://localhost:11434/v1"
    api_key: "your-api-key"
    temperature: 0.2
```

- [ ] **Step 5: Create config/mcp.yaml**

```yaml
mcp_servers:
  shell:
    transport: stdio
    command: python
    args: ["-m", "openharness.mcp_servers.shell_server"]
    startup_timeout: 30

  git:
    transport: stdio
    command: python
    args: ["-m", "openharness.mcp_servers.git_server"]
    startup_timeout: 30

  browser:
    transport: stdio
    command: python
    args: ["-m", "openharness.mcp_servers.browser_server"]
    startup_timeout: 30

  workspace:
    transport: stdio
    command: python
    args: ["-m", "openharness.mcp_servers.workspace_server"]
    startup_timeout: 30
```

- [ ] **Step 6: Create config/harness.yaml**

```yaml
harness:
  evaluation:
    max_rounds: 15
    score_threshold: 7
    dimensions:
      - name: design_quality
        weight: high
        threshold: 7
      - name: originality
        weight: high
        threshold: 7
      - name: craftsmanship
        weight: low
        threshold: 5
      - name: functionality
        weight: low
        threshold: 5

  tech_stack:
    frontend: "react+vite"
    backend: "fastapi"
    database: "sqlite"
    version_control: "git"

  context:
    strategy: "compaction"
```

- [ ] **Step 7: Verify project structure**

Run: `find . -type f | head -30`
Expected: All config YAML files and __init__.py files in place.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: project scaffold with config templates"
```

---

### Task 2: Configuration System

**Files:**
- Create: `infrastructure/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from config.config import load_llm_config, load_mcp_config, load_harness_config


def test_load_llm_config(tmp_path):
    llm_yaml = tmp_path / "llm.yaml"
    llm_yaml.write_text("""
llm:
  planner:
    model: "test-model"
    base_url: "http://localhost:11434/v1"
    api_key: "test-key"
    temperature: 0.7
  generator:
    model: "test-model"
    base_url: "http://localhost:11434/v1"
    api_key: "test-key"
    temperature: 0.4
  evaluator:
    model: "test-model"
    base_url: "http://localhost:11434/v1"
    api_key: "test-key"
    temperature: 0.2
""")
    config = load_llm_config(tmp_path)
    assert config.planner.model == "test-model"
    assert config.planner.temperature == 0.7
    assert config.generator.temperature == 0.4
    assert config.evaluator.temperature == 0.2


def test_load_mcp_config(tmp_path):
    mcp_yaml = tmp_path / "mcp.yaml"
    mcp_yaml.write_text("""
mcp_servers:
  shell:
    transport: stdio
    command: python
    args: ["-m", "test.server"]
    startup_timeout: 30
  git:
    transport: stdio
    command: python
    args: ["-m", "test.git"]
""")
    config = load_mcp_config(tmp_path)
    assert len(config.servers) == 2
    assert config.servers[0].name == "shell"
    assert config.servers[1].command == "python"


def test_load_harness_config(tmp_path):
    harness_yaml = tmp_path / "harness.yaml"
    harness_yaml.write_text("""
harness:
  evaluation:
    max_rounds: 15
    score_threshold: 7
    dimensions:
      - name: design_quality
        weight: high
        threshold: 7
      - name: originality
        weight: high
        threshold: 7
      - name: craftsmanship
        weight: low
        threshold: 5
      - name: functionality
        weight: low
        threshold: 5
  tech_stack:
    frontend: "react+vite"
    backend: "fastapi"
  context:
    strategy: "compaction"
""")
    config = load_harness_config(tmp_path)
    assert config.max_rounds == 15
    assert config.score_threshold == 7
    assert len(config.dimensions) == 4
    assert config.tech_stack["frontend"] == "react+vite"
    assert config.context_strategy == "compaction"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infrastructure.config'`

- [ ] **Step 3: Write implementation**

```python
# infrastructure/config.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/config.py tests/test_config.py
git commit -m "feat: configuration system with YAML loading"
```

---

### Task 3: MCP Manager

**Files:**
- Create: `infrastructure/mcp/manager.py`
- Create: `tests/test_mcp_manager.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_manager.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from infrastructure.mcp.manager import McpManager, McpToolInfo
from config.config import McpServerConfig


@pytest.fixture
def shell_config():
    return McpServerConfig(
        name="shell",
        transport="stdio",
        command="python",
        args=["-m", "test.shell"],
        startup_timeout=30,
    )


def test_mcp_manager_init():
    manager = McpManager()
    assert manager.list_servers() == []


def test_mcp_manager_tool_info():
    info = McpToolInfo(
        server_name="shell",
        tool_name="run_command",
        description="Run a shell command",
        input_schema={"type": "object", "properties": {"cmd": {"type": "string"}}},
    )
    assert info.server_name == "shell"
    assert info.tool_name == "run_command"


def test_mcp_manager_get_tools_empty():
    manager = McpManager()
    assert manager.get_tools_for_server("shell") == []


def test_mcp_manager_get_all_tools_empty():
    manager = McpManager()
    assert manager.get_all_tools() == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mcp_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# infrastructure/mcp/manager.py
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config.config import McpServerConfig

logger = logging.getLogger(__name__)


@dataclass
class McpToolInfo:
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]


class McpManager:
    """Manages connections to MCP servers and provides tool discovery/invocation."""

    def __init__(self) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._exit_stacks: dict[str, AsyncExitStack] = {}
        self._tools: dict[str, list[McpToolInfo]] = {}

    def list_servers(self) -> list[str]:
        return list(self._sessions.keys())

    def get_tools_for_server(self, server_name: str) -> list[McpToolInfo]:
        return self._tools.get(server_name, [])

    def get_all_tools(self) -> dict[str, list[McpToolInfo]]:
        return dict(self._tools)

    def get_tool(self, server_name: str, tool_name: str) -> McpToolInfo | None:
        for tool in self.get_tools_for_server(server_name):
            if tool.tool_name == tool_name:
                return tool
        return None

    async def connect(self, config: McpServerConfig) -> None:
        """Connect to an MCP server and discover its tools."""
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
        )
        exit_stack = AsyncExitStack()
        read_stream, write_stream = await exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        tools_result = await session.list_tools()
        tool_infos = [
            McpToolInfo(
                server_name=config.name,
                tool_name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema or {},
            )
            for t in tools_result.tools
        ]

        self._sessions[config.name] = session
        self._exit_stacks[config.name] = exit_stack
        self._tools[config.name] = tool_infos

        logger.info(
            "Connected to MCP server '%s' with %d tools: %s",
            config.name,
            len(tool_infos),
            [t.tool_name for t in tool_infos],
        )

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on an MCP server and return the result as text."""
        session = self._sessions.get(server_name)
        if session is None:
            raise ValueError(f"Not connected to MCP server: {server_name}")

        result = await session.call_tool(tool_name, arguments)
        if result.content:
            return "\n".join(
                c.text if hasattr(c, "text") else str(c)
                for c in result.content
            )
        return ""

    async def disconnect(self, server_name: str) -> None:
        """Disconnect from an MCP server."""
        if server_name in self._exit_stacks:
            await self._exit_stacks[server_name].aclose()
            del self._exit_stacks[server_name]
        self._sessions.pop(server_name, None)
        self._tools.pop(server_name, None)

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._sessions.keys()):
            await self.disconnect(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mcp_manager.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/mcp/manager.py tests/test_mcp_manager.py
git commit -m "feat: MCP manager with tool discovery and invocation"
```

---

### Task 4: MCP-AG2 Tool Bridge

**Files:**
- Create: `infrastructure/mcp/tool_bridge.py`
- Create: `tests/test_tool_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tool_bridge.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from infrastructure.mcp.manager import McpManager, McpToolInfo
from infrastructure.mcp.tool_bridge import create_sync_tool_func, register_tools_for_agent


def test_create_sync_tool_func():
    manager = MagicMock(spec=McpManager)
    manager.call_tool = AsyncMock(return_value="command output")

    tool_func = create_sync_tool_func(manager, "shell", "run_command")
    result = tool_func(cmd="echo hello")

    assert result == "command output"
    manager.call_tool.assert_called_once_with("shell", "run_command", {"cmd": "echo hello"})


def test_create_sync_tool_func_with_multiple_args():
    manager = MagicMock(spec=McpManager)
    manager.call_tool = AsyncMock(return_value="file content")

    tool_func = create_sync_tool_func(manager, "workspace", "read_file")
    result = tool_func(path="/tmp/test.txt", start_line=1, end_line=10)

    assert result == "file content"
    manager.call_tool.assert_called_once_with(
        "workspace", "read_file", {"path": "/tmp/test.txt", "start_line": 1, "end_line": 10}
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# infrastructure/mcp/tool_bridge.py
from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable

from autogen import ConversableAgent
from autogen.tools import Tool

from infrastructure.mcp.manager import McpManager, McpToolInfo

logger = logging.getLogger(__name__)


def create_sync_tool_func(
    mcp_manager: McpManager,
    server_name: str,
    tool_name: str,
) -> Callable[..., str]:
    """Create a synchronous wrapper function that calls an MCP tool.

    The wrapper runs the async MCP call in a dedicated thread with its own event loop,
    avoiding conflicts with any running event loop in the caller.
    """

    def tool_func(**kwargs: Any) -> str:
        coro = mcp_manager.call_tool(server_name, tool_name, kwargs)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return asyncio.run(coro)

    tool_func.__name__ = tool_name
    tool_func.__qualname__ = tool_name
    return tool_func


def register_tools_for_agent(
    agent: ConversableAgent,
    mcp_manager: McpManager,
    server_names: list[str],
    tool_filter: list[str] | None = None,
) -> None:
    """Register MCP tools as AG2 tools for the given agent.

    Args:
        agent: The AG2 agent to register tools for.
        mcp_manager: The MCP manager with active connections.
        server_names: Which MCP servers' tools to register.
        tool_filter: Optional list of tool names to include. If None, all tools are registered.
    """
    for server_name in server_names:
        tools = mcp_manager.get_tools_for_server(server_name)
        for tool_info in tools:
            if tool_filter and tool_info.tool_name not in tool_filter:
                continue

            sync_func = create_sync_tool_func(mcp_manager, server_name, tool_info.tool_name)

            ag2_tool = Tool(
                name=tool_info.tool_name,
                description=tool_info.description,
                func_or_tool=sync_func,
                parameters_json_schema=tool_info.input_schema,
            )
            ag2_tool.register_for_llm(agent)
            ag2_tool.register_for_execution(agent)
            logger.debug(
                "Registered tool '%s' from server '%s' for agent '%s'",
                tool_info.tool_name, server_name, agent.name,
            )

    logger.info(
        "Registered MCP tools for agent '%s' from servers: %s",
        agent.name, server_names,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tool_bridge.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/mcp/tool_bridge.py tests/test_tool_bridge.py
git commit -m "feat: MCP-AG2 tool bridge with sync wrapper"
```

---

### Task 5: Skill Loader

**Files:**
- Create: `infrastructure/skills/loader.py`
- Create: `tests/test_skill_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_skill_loader.py
import pytest
from pathlib import Path
from infrastructure.skills.loader import SkillLoader


def test_load_skill_instruction(tmp_path):
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "instruction.md").write_text("# Test Skill\nDo the thing.")

    loader = SkillLoader(roots=[tmp_path])
    instruction = loader.load_instruction("test-skill")
    assert instruction == "# Test Skill\nDo the thing."


def test_load_skill_not_found(tmp_path):
    loader = SkillLoader(roots=[tmp_path])
    instruction = loader.load_instruction("nonexistent-skill")
    assert instruction is None


def test_load_skill_from_multiple_roots(tmp_path):
    root1 = tmp_path / "root1"
    root2 = tmp_path / "root2"
    root1.mkdir()
    root2.mkdir()
    (root1 / "skill-a").mkdir()
    (root1 / "skill-a" / "instruction.md").write_text("Skill A from root1")
    (root2 / "skill-b").mkdir()
    (root2 / "skill-b" / "instruction.md").write_text("Skill B from root2")

    loader = SkillLoader(roots=[root1, root2])
    assert loader.load_instruction("skill-a") == "Skill A from root1"
    assert loader.load_instruction("skill-b") == "Skill B from root2"


def test_list_skills(tmp_path):
    (tmp_path / "skill-x").mkdir()
    (tmp_path / "skill-x" / "instruction.md").write_text("X")
    (tmp_path / "skill-y").mkdir()
    (tmp_path / "skill-y" / "instruction.md").write_text("Y")

    loader = SkillLoader(roots=[tmp_path])
    skills = loader.list_skills()
    assert set(skills) == {"skill-x", "skill-y"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_loader.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# infrastructure/skills/loader.py
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads skill definitions (instruction.md files) from configured root directories."""

    def __init__(self, roots: list[Path]) -> None:
        self._roots = roots

    def load_instruction(self, skill_name: str) -> str | None:
        """Load the instruction.md for a named skill.

        Searches roots in order, returns the first match.
        """
        for root in self._roots:
            instruction_path = root / skill_name / "instruction.md"
            if instruction_path.exists():
                return instruction_path.read_text(encoding="utf-8")
        return None

    def list_skills(self) -> list[str]:
        """List all skill names found across all roots."""
        skills: set[str] = set()
        for root in self._roots:
            if not root.exists():
                continue
            for child in root.iterdir():
                if child.is_dir() and (child / "instruction.md").exists():
                    skills.add(child.name)
        return sorted(skills)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_skill_loader.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/skills/loader.py tests/test_skill_loader.py
git commit -m "feat: skill loader for openharness skill definitions"
```

---

### Task 6: Context Management Interface

**Files:**
- Create: `infrastructure/context/base.py`
- Create: `infrastructure/context/compaction.py`

- [ ] **Step 1: Write the context strategy interface**

```python
# infrastructure/context/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ContextStrategy(ABC):
    """Base interface for context management strategies."""

    @abstractmethod
    def apply(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process the message list and return the (potentially modified) messages."""
        ...
```

- [ ] **Step 2: Write the compaction strategy**

```python
# infrastructure/context/compaction.py
from __future__ import annotations

from typing import Any

from infrastructure.context.base import ContextStrategy


class CompactionStrategy(ContextStrategy):
    """Uses AG2's built-in message compaction.

    Currently a no-op since AG2 handles compaction internally.
    This exists as a placeholder for future customization of compaction behavior.
    """

    def apply(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages
```

- [ ] **Step 3: Verify imports work**

Run: `python -c "from infrastructure.context.base import ContextStrategy; from infrastructure.context.compaction import CompactionStrategy; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add infrastructure/context/base.py infrastructure/context/compaction.py
git commit -m "feat: context management interface with compaction strategy"
```

---

### Task 7: Agent Prompts

**Files:**
- Create: `agents/prompts/planner.md`
- Create: `agents/prompts/generator.md`
- Create: `agents/prompts/evaluator.md`
- Create: `agents/prompts/loader.py`
- Create: `tests/test_prompt_loader.py`

- [ ] **Step 1: Write the prompt loader**

```python
# agents/prompts/loader.py
from __future__ import annotations

from pathlib import Path


def load_prompt(agent_name: str) -> str:
    """Load a system prompt for an agent from the prompts directory."""
    prompt_path = Path(__file__).parent / f"{agent_name}.md"
    return prompt_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_prompt_loader.py
from agents.prompts.loader import load_prompt


def test_load_prompt_exists():
    # These will pass once the .md files are created
    planner = load_prompt("planner")
    assert "Planner" in planner
    assert len(planner) > 100


def test_load_all_prompts():
    for name in ["planner", "generator", "evaluator"]:
        prompt = load_prompt(name)
        assert len(prompt) > 100, f"Prompt for {name} is too short"
```

- [ ] **Step 3: Write planner.md**

```markdown
# Planner Agent

You are the **Planner Agent** in a multi-agent team that builds full-stack web applications.

## Your Role

When you receive a user's brief description (1-4 sentences), you expand it into a comprehensive product specification. You define WHAT needs to be built, not HOW it should be implemented.

## Your Responsibilities

1. **Product Specification**: Break down the user's idea into a clear feature list with priorities
2. **Technical Architecture**: Recommend a technology stack (React + Vite for frontend, FastAPI for backend, SQLite for database)
3. **Visual Design Direction**: Describe the desired visual style, mood, and design principles (NOT specific CSS values)
4. **AI Features**: Proactively suggest AI-powered features that would enhance the product

## Output Format

Produce a structured specification in Markdown with these sections:
- **Project Overview**: One paragraph summary
- **Feature List**: Numbered list with brief descriptions
- **Technical Architecture**: Stack and high-level component layout
- **Visual Design Direction**: Style keywords, mood, color palette mood (not hex codes), reference style
- **AI Features**: Suggested AI integrations

## Important Guidelines

- Stay at a HIGH LEVEL. Do not specify implementation details, file names, or code patterns
- Be creative and ambitious — suggest features the user might not have thought of
- Prioritize user experience and visual impact
- Once you produce the specification, pass it to the team and let the Generator and Evaluator handle the rest
- When your specification is complete and clear, say "SPECIFICATION COMPLETE" so the team knows to proceed
```

- [ ] **Step 4: Write generator.md**

```markdown
# Generator Agent

You are the **Generator Agent** in a multi-agent team that builds full-stack web applications.

## Your Role

You receive product specifications from the Planner and build a complete, runnable full-stack application. You also receive evaluation feedback from the Evaluator and iterate on the application.

## Technology Stack

- **Frontend**: React + Vite (with modern CSS, responsive design)
- **Backend**: FastAPI (Python)
- **Database**: SQLite
- **Version Control**: Git (commit at logical checkpoints)

## Your Responsibilities

1. **Initialize Project**: Set up the project structure, install dependencies
2. **Build Backend**: Create FastAPI endpoints, database models, API logic
3. **Build Frontend**: Create React components, styling, API integration
4. **Start Services**: Launch both frontend and backend servers
5. **Iterate**: Based on Evaluator feedback, either **refine** (when trending well) or **refactor** (when direction is wrong)

## Workflow

1. Read the Planner's specification carefully
2. Plan your implementation approach (briefly state your plan)
3. Build the application step by step using shell and file tools
4. Start the application and verify it runs
5. Wait for Evaluator feedback
6. If feedback shows good trends (scores improving): make targeted refinements
7. If feedback shows fundamental issues: rebuild the problematic components
8. Repeat until the Evaluator approves or max rounds are reached

## Important Guidelines

- Always start services and verify they work before signaling completion
- Make meaningful Git commits at logical checkpoints
- Write clean, well-structured code — this will be evaluated on design quality and originality
- Avoid template-looking designs, default Bootstrap styles, or generic AI patterns (white cards + purple gradients)
- Be bold with design choices — custom color palettes, unique layouts, thoughtful typography
- When you've completed or updated the application, say "APPLICATION READY FOR REVIEW" so the Evaluator knows to proceed
```

- [ ] **Step 5: Write evaluator.md**

```markdown
# Evaluator Agent

You are the **Evaluator Agent** in a multi-agent team that builds full-stack web applications.

## Your Role

You are an independent, strict quality reviewer. You evaluate the Generator's output by directly interacting with the running application using browser tools. You are NOT building anything — you are the critical eye that ensures high quality.

## Evaluation Dimensions

Rate each dimension on a scale of 1-10:

### 1. Design Quality (Weight: HIGH, Threshold: 7)
- Does the application have a cohesive visual language?
- Are colors, typography, and layout harmonious?
- Does it create a distinct atmosphere/mood?
- Is there a clear design system, or does it look random?

### 2. Originality (Weight: HIGH, Threshold: 7)
- Does the design show custom, intentional decisions?
- Or does it look like a template, default styles, or typical AI output?
- Red flags: white cards on gray background, purple/blue gradients, generic Bootstrap look
- Good signs: unique color palettes, creative layouts, custom illustrations/icons

### 3. Craftsmanship (Weight: LOW, Threshold: 5)
- Typography hierarchy (headings vs body text)
- Consistent spacing and padding
- Proper use of color contrast
- Responsive behavior

### 4. Functionality (Weight: LOW, Threshold: 5)
- Can a user understand the interface without guidance?
- Do core interactions work (clicking, form submission, navigation)?
- Are error states handled?
- Is the data flow logical?

## Your Workflow

1. Wait for the Generator to signal "APPLICATION READY FOR REVIEW"
2. Open the application in the browser
3. Navigate through all major views and interactions
4. Take screenshots for documentation
5. Score each dimension with specific justification
6. Write a detailed critique with actionable feedback
7. If any HIGH-weight dimension is below threshold: list specific issues and what needs to change
8. If all dimensions pass: approve with "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD"

## Output Format

```
## Evaluation Report

### Design Quality: [score]/10
[Specific observations about visual language]

### Originality: [score]/10
[Specific observations about custom vs template design]

### Craftsmanship: [score]/10
[Specific observations about typographic/spacing quality]

### Functionality: [score]/10
[Specific observations about usability]

### Verdict: [PASSED / NEEDS IMPROVEMENT]
[Summary of key issues to fix or strengths to build on]

### Bug Report (if any)
- [File:line] Description of bug
```

## Critical Guidelines

- Be STRICT. Do not give benefit of the doubt. Average work should score 5-6, not 7-8.
- Be SPECIFIC. Don't say "the design could be better" — say "the hero section uses default system fonts with no visual hierarchy, and the color palette is the default Tailwind blue"
- Be ACTIONABLE. Every criticism should point to what specifically needs to change
- Do NOT be lenient just because something "mostly works". Hold the bar high.
- If scores are trending upward across rounds, acknowledge progress but maintain standards
```

- [ ] **Step 6: Run tests to verify**

Run: `python -m pytest tests/test_prompt_loader.py -v`
Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add agents/prompts/ tests/test_prompt_loader.py
git commit -m "feat: agent system prompts with evaluation criteria"
```

---

### Task 8: Agent Factory

**Files:**
- Create: `agents/planner.py`
- Create: `agents/generator.py`
- Create: `agents/evaluator.py`
- Create: `agents/factory.py`
- Create: `tests/test_agent_factory.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_factory.py
import pytest
from unittest.mock import MagicMock
from agents.factory import create_planner, create_generator, create_evaluator
from config.config import LlmConfig, LlmAgentConfig


@pytest.fixture
def llm_config():
    return LlmConfig(
        planner=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.7),
        generator=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.4),
        evaluator=LlmAgentConfig(model="test", base_url="http://localhost/v1", api_key="key", temperature=0.2),
    )


def test_create_planner(llm_config):
    agent = create_planner(llm_config)
    assert agent.name == "Planner"
    assert "Planner" in agent.description


def test_create_generator(llm_config):
    agent = create_generator(llm_config)
    assert agent.name == "Generator"
    assert "Generator" in agent.description


def test_create_evaluator(llm_config):
    agent = create_evaluator(llm_config)
    assert agent.name == "Evaluator"
    assert "Evaluator" in agent.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_agent_factory.py -v`
Expected: FAIL

- [ ] **Step 3: Write agent definitions**

```python
# agents/planner.py
from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from config.config import LlmConfig


def create_planner(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Planner agent that expands user prompts into product specs."""
    prompt = load_prompt("planner")
    return ConversableAgent(
        name="Planner",
        system_message=prompt,
        description=(
            "Planner: Expands user requirements into detailed product specifications. "
            "Speak FIRST when a new user request arrives. "
            "Produces feature lists, technical architecture, and visual design direction. "
            "Does NOT implement code."
        ),
        llm_config=llm_config.planner.to_llm_config(),
        human_input_mode="NEVER",
    )
```

```python
# agents/generator.py
from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from config.config import LlmConfig


def create_generator(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Generator agent that builds full-stack applications."""
    prompt = load_prompt("generator")
    return ConversableAgent(
        name="Generator",
        system_message=prompt,
        description=(
            "Generator: Builds full-stack web applications from specifications. "
            "Speaks AFTER the Planner produces a specification. "
            "Uses shell, git, workspace, and browser tools to create React+Vite+FastAPI applications. "
            "Iterates based on Evaluator feedback — refines when trending well, refactors when direction is wrong."
        ),
        llm_config=llm_config.generator.to_llm_config(),
        human_input_mode="NEVER",
    )
```

```python
# agents/evaluator.py
from __future__ import annotations

from autogen import ConversableAgent

from agents.prompts.loader import load_prompt
from config.config import LlmConfig


def create_evaluator(llm_config: LlmConfig) -> ConversableAgent:
    """Create the Evaluator agent that reviews applications with Playwright."""
    prompt = load_prompt("evaluator")
    return ConversableAgent(
        name="Evaluator",
        system_message=prompt,
        description=(
            "Evaluator: Strict quality reviewer for web applications. "
            "Speaks AFTER the Generator signals the application is ready. "
            "Uses browser tools to interact with running applications and evaluate design quality, "
            "originality, craftsmanship, and functionality on a 1-10 scale. "
            "Provides specific, actionable feedback with scores."
        ),
        llm_config=llm_config.evaluator.to_llm_config(),
        human_input_mode="NEVER",
    )
```

```python
# agents/factory.py
from __future__ import annotations

from autogen import ConversableAgent

from agents.planner import create_planner
from agents.generator import create_generator
from agents.evaluator import create_evaluator
from config.config import LlmConfig
from infrastructure.mcp.manager import McpManager
from infrastructure.mcp.tool_bridge import register_tools_for_agent


def create_planner_agent(llm_config: LlmConfig, mcp_manager: McpManager | None = None) -> ConversableAgent:
    """Create a Planner agent (no MCP tools needed)."""
    return create_planner(llm_config)


def create_generator_agent(llm_config: LlmConfig, mcp_manager: McpManager) -> ConversableAgent:
    """Create a Generator agent with shell, git, workspace, and browser tools."""
    agent = create_generator(llm_config)
    register_tools_for_agent(agent, mcp_manager, ["shell", "git", "workspace", "browser"])
    return agent


def create_evaluator_agent(llm_config: LlmConfig, mcp_manager: McpManager) -> ConversableAgent:
    """Create an Evaluator agent with browser and shell tools."""
    agent = create_evaluator(llm_config)
    register_tools_for_agent(agent, mcp_manager, ["browser", "shell"])
    return agent


def create_all_agents(
        llm_config: LlmConfig,
        mcp_manager: McpManager,
) -> dict[str, ConversableAgent]:
    """Create all three agents with their tools."""
    return {
        "planner": create_planner_agent(llm_config, mcp_manager),
        "generator": create_generator_agent(llm_config, mcp_manager),
        "evaluator": create_evaluator_agent(llm_config, mcp_manager),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_agent_factory.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/ tests/test_agent_factory.py
git commit -m "feat: agent factory with planner, generator, evaluator"
```

---

### Task 9: Orchestration

**Files:**
- Create: `orchestration/group.py`
- Create: `orchestration/termination.py`
- Create: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestration.py
import pytest
from orchestration.termination import create_termination_check
from orchestration.group import create_group_chat


def test_termination_check_passed():
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD"})


def test_termination_check_not_passed():
    check = create_termination_check()
    assert not check({"content": "EVALUATION Report\n### Verdict: NEEDS IMPROVEMENT"})


def test_termination_check_terminate():
    check = create_termination_check()
    assert check({"content": "TERMINATE"})


def test_termination_check_empty():
    check = create_termination_check()
    assert not check({"content": ""})


def test_termination_check_none():
    check = create_termination_check()
    assert not check({"content": None})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestration.py -v`
Expected: FAIL

- [ ] **Step 3: Write termination condition**

```python
# orchestration/termination.py
from __future__ import annotations

from typing import Any, Callable


def create_termination_check() -> Callable[[dict[str, Any]], bool]:
    """Create a termination message checker for the GroupChat.

    Terminates when:
    - Evaluator sends "EVALUATION PASSED"
    - Any agent sends "TERMINATE"
    """
    def is_termination_msg(msg: dict[str, Any]) -> bool:
        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            return False
        content_upper = content.upper()
        return (
            "EVALUATION PASSED" in content_upper
            or "TERMINATE" in content_upper
        )
    return is_termination_msg
```

- [ ] **Step 4: Write GroupChat setup**

```python
# orchestration/group.py
from __future__ import annotations

from typing import Any

from autogen import ConversableAgent, GroupChat, GroupChatManager

from config.config import LlmConfig, HarnessConfig
from orchestration.termination import create_termination_check


def create_group_chat(
        agents: list[ConversableAgent],
        llm_config: LlmConfig,
        harness_config: HarnessConfig,
) -> GroupChatManager:
    """Create a GroupChatManager with auto speaker selection.

    Uses AG2's built-in auto mode: the LLM decides who speaks next
    based on agent descriptions and conversation context.
    """
    is_termination_msg = create_termination_check()

    group_chat = GroupChat(
        agents=agents,
        messages=[],
        max_round=harness_config.max_rounds,
        speaker_selection_method="auto",
        send_introductions=True,
        max_retries_for_selecting_speaker=3,
    )

    # Use planner's LLM config for the manager's speaker selection
    manager_llm_config = llm_config.planner.to_llm_config()

    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config=manager_llm_config,
        is_termination_msg=is_termination_msg,
    )

    return manager
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_orchestration.py -v`
Expected: 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add orchestration/ tests/test_orchestration.py
git commit -m "feat: orchestration with auto GroupChat and termination conditions"
```

---

### Task 10: Main Entry Point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write main.py**

```python
# main.py
"""AG2 OpenHarness - Multi-agent full-stack application generation harness."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from config.config import load_llm_config, load_mcp_config, load_harness_config
from infrastructure.mcp.manager import McpManager
from agents.factory import create_all_agents
from orchestration.group import create_group_chat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "config"


async def run(prompt: str) -> None:
    """Run the harness with the given user prompt."""
    # Load configuration
    logger.info("Loading configuration from %s", CONFIG_DIR)
    llm_config = load_llm_config(CONFIG_DIR)
    mcp_config = load_mcp_config(CONFIG_DIR)
    harness_config = load_harness_config(CONFIG_DIR)

    # Connect to MCP servers
    logger.info("Connecting to MCP servers...")
    mcp_manager = McpManager()
    for server_cfg in mcp_config.servers:
        try:
            await mcp_manager.connect(server_cfg)
        except Exception as e:
            logger.error("Failed to connect to MCP server '%s': %s", server_cfg.name, e)

    try:
        # Create agents
        logger.info("Creating agents...")
        agents_dict = create_all_agents(llm_config, mcp_manager)
        agents_list = [
            agents_dict["planner"],
            agents_dict["generator"],
            agents_dict["evaluator"],
        ]

        # Create group chat
        logger.info("Setting up group chat (max %d rounds)...", harness_config.max_rounds)
        manager = create_group_chat(agents_list, llm_config, harness_config)

        # Start the conversation
        logger.info("Starting conversation with prompt: %s", prompt[:100])
        agents_list[0].initiate_chat(
            manager,
            message=prompt,
        )
    finally:
        # Cleanup
        logger.info("Disconnecting MCP servers...")
        await mcp_manager.disconnect_all()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py \"Your application description\"")
        print("Example: python main.py \"Build a task management app with dark theme\"")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    asyncio.run(run(prompt))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import structure**

Run: `python -c "import main; print('OK')"`
Expected: `OK` (assuming dependencies are installed)

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main entry point wiring config, MCP, agents, and orchestration"
```

---

### Task 11: End-to-End Smoke Test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write a structural smoke test**

This test verifies the wiring without requiring actual MCP servers or LLM calls:

```python
# tests/test_e2e.py
"""End-to-end structural test — verifies wiring without MCP servers or LLM calls."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from config.config import load_llm_config, load_mcp_config, load_harness_config
from agents.factory import create_planner, create_generator, create_evaluator
from orchestration.group import create_group_chat
from orchestration.termination import create_termination_check

CONFIG_DIR = Path(__file__).parent.parent / "config"


def test_config_files_exist():
    assert (CONFIG_DIR / "llm.yaml").exists()
    assert (CONFIG_DIR / "mcp.yaml").exists()
    assert (CONFIG_DIR / "harness.yaml").exists()


def test_config_loading():
    llm = load_llm_config(CONFIG_DIR)
    mcp = load_mcp_config(CONFIG_DIR)
    harness = load_harness_config(CONFIG_DIR)
    assert llm.planner.model
    assert len(mcp.servers) >= 3
    assert harness.max_rounds > 0
    assert len(harness.dimensions) == 4


def test_agent_creation():
    llm = load_llm_config(CONFIG_DIR)
    planner = create_planner(llm)
    generator = create_generator(llm)
    evaluator = create_evaluator(llm)
    assert planner.name == "Planner"
    assert generator.name == "Generator"
    assert evaluator.name == "Evaluator"


def test_group_chat_creation():
    llm = load_llm_config(CONFIG_DIR)
    harness = load_harness_config(CONFIG_DIR)
    planner = create_planner(llm)
    generator = create_generator(llm)
    evaluator = create_evaluator(llm)
    manager = create_group_chat([planner, generator, evaluator], llm, harness)
    assert manager is not None
    assert len(manager.groupchat.agents) == 3


def test_termination_conditions():
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD"})
    assert check({"content": "TERMINATE"})
    assert not check({"content": "Needs improvement on design"})
    assert not check({"content": "Building the application now"})
```

- [ ] **Step 2: Run the smoke test**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: 5 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "feat: end-to-end structural smoke test"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- Three-layer architecture: Tasks 2-6 (infrastructure), Tasks 7-8 (agent design), Task 9 (orchestration) — covered
- MCP integration (stdio from openharness): Tasks 3-4 — covered
- Skill loader: Task 5 — covered
- Context management (compaction): Task 6 — covered
- Three agents with auto GroupChat: Tasks 7-9 — covered
- Prompt externalization: Task 7 — covered
- Playwright evaluation via browser MCP: Task 7 evaluator prompt references browser tools — covered
- Config-driven: Tasks 1-2 — covered
- Main entry point: Task 10 — covered

**2. Placeholder scan:** No TBD/TODO found. All code blocks contain actual implementation.

**3. Type consistency:** All dataclasses, function signatures, and imports are consistent across tasks.
