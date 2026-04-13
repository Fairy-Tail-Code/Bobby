# FastAPI Runtime Design Spec

> Date: 2026-04-13
> Status: Approved
> Scope: Convert CLI-based AG2 OpenHarness into a FastAPI runtime service

---

## 1. Background

The current system is CLI-only: `uv run main.py "prompt"`. This design wraps the entire execution into a FastAPI HTTP/WebSocket service, enabling remote invocation, real-time progress tracking, HITL via WebSocket, and scheduled background tasks.

---

## 2. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Concurrency model | `asyncio.Semaphore(4)` | Limited concurrent swarm tasks (2-4) |
| Status tracking | WebSocket bidirectional | Real-time push + HITL input |
| Scheduler | APScheduler (in-process) | No external infrastructure, supports cron |
| Database | PostgreSQL + SQLAlchemy async | Persistent task records and session history |
| API structure | Modular Router (`include_router`) | Easy to add new modules |
| HITL | `WebSocketUserProxyAgent` | Replace stdin with WebSocket bidirectional bridge |

---

## 3. Directory Structure (New Files Only)

```
api/
├── __init__.py
├── router_registry.py           # Central router registration
├── tasks/
│   ├── __init__.py
│   ├── router.py                # POST /tasks, GET /tasks, GET /tasks/{id}
│   ├── ws.py                    # WS /tasks/{id}/stream
│   └── schemas.py               # Pydantic models
├── scheduler/
│   ├── __init__.py
│   ├── router.py                # GET/POST/DELETE /scheduler/jobs
│   └── schemas.py
└── memory/                      # Placeholder for future memory API
    ├── __init__.py
    └── router.py

runtime/
├── __init__.py
├── app.py                       # FastAPI app factory
├── lifecycle.py                 # startup/shutdown hooks
├── task_manager.py              # Task dispatch + semaphore + event broadcast
└── hitl_bridge.py               # WebSocket <-> Agent HITL bridge

scheduler/
├── __init__.py
├── scheduler.py                 # APScheduler wrapper
└── jobs/
    ├── __init__.py
    └── dream.py                 # Memory dream consolidation job

db/
├── __init__.py
├── engine.py                    # SQLAlchemy async engine + session factory
├── models.py                    # ORM models (TaskRecord, SessionMessage)
├── migrations/                  # Alembic migrations
└── repos/
    ├── __init__.py
    ├── task_repo.py
    └── session_repo.py
```

**Modified existing files** (minimal changes):
- `agents/user.py` — add `WebSocketUserProxyAgent`
- `agents/factory.py` — add `create_ws_user_agent()` factory method
- `main.py` — refactor `run()` to accept injected dependencies (bridge, event_callback)
- `infrastructure/config.py` — add `ServerConfig`, `DatabaseConfig`
- `config/harness.yaml` — add `server` and `database` sections

---

## 4. Task Lifecycle

### 4.1 Create Task

```
POST /api/v1/tasks
Body: {"prompt": "Build a todo app with dark theme"}
Response: {"task_id": "uuid", "status": "pending", "created_at": "..."}
```

- Creates a `TaskRecord` in PostgreSQL with `status=pending`
- Enqueues task execution behind `asyncio.Semaphore(4)`
- Returns immediately with task_id

### 4.2 Stream Task Events (WebSocket)

```
WS /api/v1/tasks/{task_id}/stream
```

Server pushes events:

```json
{"type": "status", "data": {"status": "running"}}
{"type": "agent_message", "data": {"agent": "planner", "content": "..."}}
{"type": "handoff", "data": {"from": "planner", "to": "generator"}}
{"type": "hitl_input_required", "data": {"agent": "user", "prompt": "Please clarify..."}}
{"type": "completed", "data": {"last_speaker": "evaluator", "summary": "..."}}
{"type": "error", "data": {"message": "LLM rate limit exceeded"}}
```

Client sends HITL input:

```json
{"type": "hitl_response", "data": {"content": "I want React + Express"}}
```

### 4.3 Query Task

```
GET /api/v1/tasks/{task_id}
Response: {"task_id": "...", "status": "completed", "result": "...", "messages": [...]}
```

### 4.4 List Tasks

```
GET /api/v1/tasks?status=completed&limit=20&offset=0
Response: {"tasks": [...], "total": 42}
```

---

## 5. HITL WebSocket Bridge

### 5.1 Problem

AG2's `UserProxyAgent` blocks on `input()` (stdin) when `human_input_mode="ALWAYS"`. In a FastAPI server, there is no stdin. We must replace this with an async WebSocket-based input mechanism.

### 5.2 Solution: HITLBridge

```python
class HITLBridge:
    """Bridges WebSocket bidirectional communication and AG2 UserProxyAgent input."""

    def __init__(self):
        self._pending: dict[str, asyncio.Future] = {}  # task_id -> Future
        self._ws_connections: dict[str, WebSocket] = {}  # task_id -> WebSocket

    def register_ws(self, task_id: str, ws: WebSocket):
        self._ws_connections[task_id] = ws

    def unregister_ws(self, task_id: str):
        self._ws_connections.pop(task_id, None)

    async def request_input(self, task_id: str, prompt: str) -> str:
        """Called by WebSocketUserProxyAgent.a_get_human_input().
        Sends hitl_input_required event via WebSocket, then awaits client response."""
        future = asyncio.get_event_loop().create_future()
        self._pending[task_id] = future
        ws = self._ws_connections[task_id]
        await ws.send_json({
            "type": "hitl_input_required",
            "data": {"agent": "user", "prompt": prompt}
        })
        return await future

    def provide_input(self, task_id: str, content: str):
        """Called by WebSocket endpoint when client sends hitl_response.
        Resolves the pending Future."""
        if future := self._pending.pop(task_id, None):
            future.set_result(content)

    async def send_event(self, task_id: str, event_type: str, data: dict):
        ws = self._ws_connections.get(task_id)
        if ws:
            await ws.send_json({"type": event_type, "data": data})
```

### 5.3 WebSocketUserProxyAgent

```python
class WebSocketUserProxyAgent(UserProxyAgent):
    def __init__(self, hitl_bridge: HITLBridge, task_id: str, **kwargs):
        super().__init__(**kwargs)
        self._bridge = hitl_bridge
        self._task_id = task_id

    async def a_get_human_input(self, prompt: str) -> str:
        return await self._bridge.request_input(self._task_id, prompt)
```

### 5.4 WebSocket Endpoint Flow

```python
@router.websocket("/{task_id}/stream")
async def task_stream(ws: WebSocket, task_id: str):
    await ws.accept()
    hitl_bridge.register_ws(task_id, ws)
    try:
        while True:
            msg = await ws.receive_json()
            if msg["type"] == "hitl_response":
                hitl_bridge.provide_input(task_id, msg["data"]["content"])
    except WebSocketDisconnect:
        pass
    finally:
        hitl_bridge.unregister_ws(task_id)
```

---

## 6. Task Manager

```python
class TaskManager:
    def __init__(self, max_concurrent: int = 4):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._hitl_bridge = HITLBridge()
        self._running: dict[str, asyncio.Task] = {}

    async def submit(self, task_id: str, prompt: str) -> None:
        """Submit a task for execution (non-blocking)."""
        async_task = asyncio.create_task(self._execute(task_id, prompt))
        self._running[task_id] = async_task

    async def _execute(self, task_id: str, prompt: str) -> None:
        async with self._semaphore:
            await update_task_status(task_id, "running")
            try:
                result = await run(
                    prompt,
                    hitl_bridge=self._hitl_bridge,
                    task_id=task_id,
                    event_callback=self._make_callback(task_id),
                )
                await update_task_status(task_id, "completed", result=result)
            except Exception as e:
                await update_task_status(task_id, "failed", error=str(e))

    def _make_callback(self, task_id: str):
        async def callback(event_type: str, data: dict):
            await self._hitl_bridge.send_event(task_id, event_type, data)
        return callback
```

---

## 7. Scheduler

### 7.1 Wrapper

```python
class TaskScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()

    def start(self):
        self._scheduler.start()

    def shutdown(self):
        self._scheduler.shutdown()

    def add_job(self, job_id: str, func, trigger, **kwargs):
        self._scheduler.add_job(func, trigger, id=job_id, **kwargs)

    def remove_job(self, job_id: str):
        self._scheduler.remove_job(job_id)

    def list_jobs(self) -> list[dict]:
        jobs = self._scheduler.get_jobs()
        return [{"id": j.id, "next_run": str(j.next_run_time)} for j in jobs]
```

### 7.2 API

```
GET    /api/v1/scheduler/jobs          — List all scheduled jobs
POST   /api/v1/scheduler/jobs          — Add a new job
DELETE /api/v1/scheduler/jobs/{job_id} — Remove a job
```

### 7.3 Built-in Jobs

- `dream_consolidation` — Memory dream consolidation (cron, configurable interval)

---

## 8. Database

### 8.1 ORM Models

```python
class TaskRecord(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)      # UUID
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))                 # pending|running|completed|failed
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    messages: Mapped[list["SessionMessage"]] = relationship(back_populates="task")

class SessionMessage(Base):
    __tablename__ = "session_messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    agent_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))                  # assistant|user|tool
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    task: Mapped["TaskRecord"] = relationship(back_populates="messages")
```

### 8.2 Engine

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

def create_engine(database_url: str):
    return create_async_engine(database_url, echo=False, pool_size=10)

def create_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)
```

### 8.3 Migrations

Use Alembic for schema migrations. Initial migration creates `tasks` and `session_messages` tables.

---

## 9. Configuration (harness.yaml additions)

```yaml
harness:
  server:
    host: "0.0.0.0"
    port: 8000
    max_concurrent_tasks: 4
    cors_origins:
      - "*"

  database:
    url: "postgresql+asyncpg://user:pass@localhost:5432/openharness"
    pool_size: 10

  scheduler:
    enabled: true
    jobs:
      - id: dream_consolidation
        trigger: interval
        hours: 24
        enabled: false  # Initially disabled, enable after memory system is built
```

### Corresponding Config Classes

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
    id: str
    trigger: str  # interval | cron
    hours: int = 24
    enabled: bool = True

@dataclass
class SchedulerConfig:
    enabled: bool = True
    jobs: list[SchedulerJobConfig] = field(default_factory=list)
```

---

## 10. App Lifecycle

```python
# runtime/lifecycle.py

async def startup(app: FastAPI):
    # 1. Initialize database
    engine = create_engine(config.database.url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.state.db_session = create_session_factory(engine)

    # 2. Initialize task manager
    app.state.task_manager = TaskManager(max_concurrent=config.server.max_concurrent_tasks)

    # 3. Start scheduler
    if config.scheduler.enabled:
        app.state.scheduler = TaskScheduler()
        app.state.scheduler.start()
        for job in config.scheduler.jobs:
            if job.enabled:
                register_job(app.state.scheduler, job)

async def shutdown(app: FastAPI):
    # 1. Stop scheduler
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()
    # 2. Cancel running tasks
    if hasattr(app.state, 'task_manager'):
        await app.state.task_manager.cancel_all()
    # 3. Dispose database engine
    if hasattr(app.state, 'db_engine'):
        await app.state.db_engine.dispose()
```

---

## 11. Changes to Existing Code

### 11.1 `main.py` — `run()` function

Add optional parameters for injected dependencies:

```python
async def run(
    prompt: str,
    *,
    hitl_bridge: HITLBridge | None = None,
    task_id: str | None = None,
    event_callback: Callable[[str, dict], Awaitable[None]] | None = None,
) -> dict:
```

When `hitl_bridge` is provided, use `WebSocketUserProxyAgent` instead of `UserProxyAgent`. When `event_callback` is provided, broadcast agent messages and handoffs as events.

When both are `None` (CLI mode), behavior is identical to current — stdin-based `UserProxyAgent`.

### 11.2 `agents/user.py`

Add `WebSocketUserProxyAgent` class alongside existing `create_user()`:

```python
def create_ws_user(hitl_bridge: HITLBridge, task_id: str) -> WebSocketUserProxyAgent:
    return WebSocketUserProxyAgent(
        name="user",
        hitl_bridge=hitl_bridge,
        task_id=task_id,
        human_input_mode="ALWAYS",
        code_execution_config={"work_dir": r"...", "use_docker": False},
    )
```

### 11.3 `agents/factory.py`

Add `create_ws_user_agent()` and modify `create_all_agents()` to accept optional `hitl_bridge` + `task_id`:

```python
def create_all_agents(
    llm_config, mcp_manager, skill_registry, harness_config,
    *, hitl_bridge=None, task_id=None,
):
    ...
    if hitl_bridge and task_id:
        agents["user"] = create_ws_user_agent(hitl_bridge, task_id)
    else:
        agents["user"] = create_user_agent(llm_config)
```

---

## 12. Entry Point

```python
# runtime/app.py

def create_app() -> FastAPI:
    app = FastAPI(title="AG2 OpenHarness", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
    register_all_routers(app)
    app.add_event_handler("startup", lambda: startup(app))
    app.add_event_handler("shutdown", lambda: shutdown(app))
    return app

# New entry: uv run python -m runtime
# Or: uv run uvicorn runtime.app:create_app --factory --host 0.0.0.0 --port 8000
```

---

## 13. Dependency Additions (pyproject.toml)

```toml
dependencies = [
    # ... existing ...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "apscheduler>=3.10.0",
    "alembic>=1.13.0",
    "websockets>=12.0",
]
```

---

## 14. Extensibility: Adding a New API Module

To add a new API module (e.g., "memory"):

1. Create `api/memory/router.py` with a `APIRouter`
2. Create `api/memory/schemas.py` with Pydantic models
3. Add one line in `api/router_registry.py`: `app.include_router(memory_router, prefix="/api/v1/memory", tags=["memory"])`

No other files need modification.
