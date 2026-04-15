# FastAPI Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the CLI-based AG2 OpenHarness into a FastAPI HTTP/WebSocket service with task management, HITL via WebSocket, and in-process scheduling.

**Architecture:** FastAPI app wraps the existing `run()` function. Tasks are submitted via REST API, executed with semaphore-controlled concurrency, and streamed via WebSocket. HITL is bridged through `WebSocketUserProxyAgent` overriding `a_get_human_input`. PostgreSQL persists task records and session messages.

**Tech Stack:** FastAPI, uvicorn, SQLAlchemy async + asyncpg, APScheduler, WebSocket, Pydantic v2

**Spec:** `docs/superpowers/specs/2026-04-13-fastapi-runtime-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `runtime/__init__.py` | Package init |
| `runtime/app.py` | FastAPI app factory |
| `runtime/lifecycle.py` | startup/shutdown hooks |
| `runtime/task_manager.py` | Task dispatch + semaphore + event broadcast |
| `runtime/hitl_bridge.py` | WebSocket <-> Agent HITL bridge |
| `db/__init__.py` | Package init |
| `db/engine.py` | SQLAlchemy async engine + session factory |
| `db/models.py` | ORM models (TaskRecord, SessionMessage) |
| `db/repos/__init__.py` | Package init |
| `db/repos/task_repo.py` | Task CRUD |
| `db/repos/session_repo.py` | Session message CRUD |
| `api/__init__.py` | Package init |
| `api/router_registry.py` | Central router registration |
| `api/tasks/__init__.py` | Package init |
| `api/tasks/router.py` | POST/GET tasks |
| `api/tasks/ws.py` | WebSocket streaming |
| `api/tasks/schemas.py` | Pydantic models |
| `api/scheduler/__init__.py` | Package init |
| `api/scheduler/router.py` | Scheduler CRUD API |
| `api/scheduler/schemas.py` | Pydantic models |
| `scheduler/__init__.py` | Package init |
| `scheduler/scheduler.py` | APScheduler wrapper |
| `tests/test_runtime.py` | Runtime integration tests |
| `tests/test_task_manager.py` | Task manager tests |
| `tests/test_hitl_bridge.py` | HITL bridge tests |
| `tests/test_db.py` | Database model + repo tests |
| `tests/test_api_tasks.py` | Tasks API tests |

### Modified Files

| File | Change |
|------|--------|
| `pyproject.toml` | Add fastapi, uvicorn, sqlalchemy, asyncpg, apscheduler, alembic, websockets |
| `infrastructure/config.py` | Add ServerConfig, DatabaseConfig, SchedulerJobConfig, SchedulerConfig |
| `config/harness.yaml` | Add server, database, scheduler sections |
| `agents/user.py` | Add WebSocketUserProxyAgent + create_ws_user() |
| `agents/factory.py` | Add hitl_bridge/task_id params to create_all_agents |
| `main.py` | Add hitl_bridge, task_id, event_callback params to run() |

---

## Task 1: Dependencies + Config

**Files:**
- Modify: `pyproject.toml`
- Modify: `infrastructure/config.py`
- Modify: `config/harness.yaml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add these to the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "ag2[openai]>=0.7.0",
    "mcp>=1.27.0",
    "pip>=26.0.1",
    "playwright>=1.58.0",
    "pyyaml>=6.0.3",
    "tiktoken>=0.9.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "apscheduler>=3.10.0",
    "alembic>=1.13.0",
    "websockets>=12.0",
    "aiosqlite>=0.20.0",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync`

- [ ] **Step 3: Add config dataclasses to `infrastructure/config.py`**

Append after `HarnessConfig` class (before `_load_yaml`):

```python
@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    max_concurrent_tasks: int = 4
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


@dataclass
class DatabaseConfig:
    url: str = "postgresql+asyncpg://localhost/openharness"
    pool_size: int = 10


@dataclass
class SchedulerJobConfig:
    id: str = ""
    trigger: str = "interval"
    hours: int = 24
    enabled: bool = True


@dataclass
class SchedulerConfig:
    enabled: bool = True
    jobs: list[SchedulerJobConfig] = field(default_factory=list)
```

- [ ] **Step 4: Add config sections to `config/harness.yaml`**

Append at the end of the file:

```yaml
  server:
    host: "0.0.0.0"
    port: 8000
    max_concurrent_tasks: 4
    cors_origins:
      - "*"

  database:
    url: "postgresql+asyncpg://localhost:5432/openharness"
    pool_size: 10

  scheduler:
    enabled: true
    jobs: []
```

- [ ] **Step 5: Update `load_harness_config` to parse new sections**

In `infrastructure/config.py`, update the `load_harness_config` function:

```python
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

    server_raw = raw.get("server", {})
    server = ServerConfig(
        host=server_raw.get("host", "0.0.0.0"),
        port=server_raw.get("port", 8000),
        max_concurrent_tasks=server_raw.get("max_concurrent_tasks", 4),
        cors_origins=server_raw.get("cors_origins", ["*"]),
    )

    db_raw = raw.get("database", {})
    database = DatabaseConfig(
        url=db_raw.get("url", "postgresql+asyncpg://localhost/openharness"),
        pool_size=db_raw.get("pool_size", 10),
    )

    sched_raw = raw.get("scheduler", {})
    scheduler_jobs = [
        SchedulerJobConfig(**j) for j in sched_raw.get("jobs", [])
    ]
    scheduler = SchedulerConfig(
        enabled=sched_raw.get("enabled", True),
        jobs=scheduler_jobs,
    )

    return HarnessConfig(
        max_rounds=eval_cfg["max_rounds"],
        score_threshold=eval_cfg["score_threshold"],
        dimensions=dimensions,
        tech_stack=raw.get("tech_stack", {}),
        context=context,
        server=server,
        database=database,
        scheduler=scheduler,
    )
```

Update `HarnessConfig` dataclass to include the new fields:

```python
@dataclass
class HarnessConfig:
    max_rounds: int = 15
    score_threshold: int = 7
    dimensions: list[EvaluationDimension] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    context: ContextConfig = field(default_factory=ContextConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
```

- [ ] **Step 6: Run existing tests to verify nothing broke**

Run: `uv run pytest tests/test_config.py -v`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock infrastructure/config.py config/harness.yaml
git commit -m "feat: add FastAPI runtime dependencies and server/database/scheduler config"
```

---

## Task 2: Database Models + Engine

**Files:**
- Create: `db/__init__.py`
- Create: `db/engine.py`
- Create: `db/models.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Create `db/__init__.py`**

```python

