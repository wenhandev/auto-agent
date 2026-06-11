## ADDED Requirements

### Requirement: SQLite Persistence Layer

The backend SHALL persist all platform state in a single SQLite database located at `backend/data/auto_agent.db`. The schema SHALL be defined in `backend/app/db/models.py` using `sqlmodel` and SHALL be created on application startup via `SQLModel.metadata.create_all(engine)`.

#### Scenario: Tables created on first boot

- **WHEN** the FastAPI app starts and `backend/data/auto_agent.db` does not exist
- **THEN** the startup hook SHALL create the file, create every table defined in `models.py`, and SHALL NOT crash on subsequent restarts when the tables already exist.

#### Scenario: Session dependency

- **WHEN** a router needs DB access
- **THEN** it SHALL receive a `Session` via FastAPI's `Depends(get_session)` and SHALL NOT instantiate engines or sessions directly.

### Requirement: Workflow And WorkflowVersion Tables

The `Workflow` table SHALL store metadata (name, description, timestamps, owner_id reserved, current_version_id pointer). The `WorkflowVersion` table SHALL store the full `Workflow` JSON shape per version (the canonical contract reused unchanged from the MVP).

#### Scenario: Creating a workflow seeds a version

- **WHEN** a new `Workflow` row is created (whether via `POST /api/workflows`, `POST /api/workflow/generate`, or the chat editor producing the first version)
- **THEN** a `WorkflowVersion` row SHALL be created with `version_number=1` and `workflow_json` set to a valid `Workflow`, and `Workflow.current_version_id` SHALL point to it.

#### Scenario: Editing produces a new version

- **WHEN** the chat editor applies a patch or full replacement that validates against `Workflow`
- **THEN** a new `WorkflowVersion` row SHALL be inserted with `version_number = previous + 1`, `Workflow.current_version_id` SHALL be updated to the new row, and the prior version SHALL NOT be mutated.

**Design rationale (retention):** every chat-driven edit appends a new `WorkflowVersion` and the platform retains **all** versions indefinitely with no pruning policy. This is intentional simplicity for a SQLite-backed single-user platform; row counts are small in practice and a retention knob is a future change if the database ever grows uncomfortably.

### Requirement: ChatSession And ChatMessage Tables

Each `Workflow` SHALL have exactly one active `ChatSession`. Each turn (user or assistant) SHALL be persisted as a `ChatMessage` with `role`, `content`, `created_at`, and — for assistant turns that produce a version — `patch_json` and `workflow_version_id`.

#### Scenario: Auto-create session on first chat read

- **WHEN** the frontend requests `GET /api/chat/{session_id}` for a workflow that has no `ChatSession`
- **THEN** the backend SHALL create one (the session id is the workflow's session id, exposed in `GET /api/workflows/{id}` payload).

#### Scenario: Assistant message references new version

- **WHEN** the editor agent returns a valid patch and the patch produces `WorkflowVersion` #5
- **THEN** the appended assistant `ChatMessage` SHALL have `workflow_version_id = 5` and `patch_json` set to the serialized op list.

### Requirement: Run And RunEvent Tables

The `Run` table SHALL record `workflow_id`, `workflow_version_id`, `status ∈ {queued, running, completed, failed, aborted}`, `queued_at`, `started_at`, `finished_at`, and an `error` string for failed runs. The `RunEvent` table SHALL store the verbatim JSON frames emitted by `/ws/run`, keyed by `(run_id, seq)`. Event types SHALL include `run_queued | run_started | node_started | node_progress | node_completed | node_failed | run_completed | run_failed | run_aborted`.

#### Scenario: Run is created in queued state

- **WHEN** the client calls `POST /api/runs { workflow_id }`
- **THEN** a `Run` row SHALL be inserted with `status="queued"`, `workflow_version_id` set to the workflow's current version, `queued_at=now()`, and `started_at`/`finished_at` left null until the scheduler picks it up.

#### Scenario: Events persisted in order

- **WHEN** the executor emits a sequence of events during a persisted run
- **THEN** each event SHALL be inserted as a `RunEvent` row with a monotonically increasing `seq`, and the JSON payload SHALL be identical to what was forwarded over the WebSocket.

#### Scenario: Aborted run on disconnect or explicit abort

- **WHEN** the WebSocket for a persisted run closes before a `run_completed` / `run_failed` event was written, OR the client sends `{type:"abort", run_id}`
- **THEN** the server SHALL set the `Run.status` to `"aborted"`, write `finished_at`, and persist a `run_aborted` event row.

### Requirement: Credential And LlmConfig Tables

The `Credential` table SHALL hold `name` (unique, used for lookup-by-name from workflow nodes), `kind`, an `encrypted_blob` of the serialized field map, a `hint` string for masked display, and timestamps. The `LlmConfig` table SHALL hold `provider`, `model`, `encrypted_api_key`, optional `base_url`, optional `extra_json`, an `is_active` boolean, and timestamps. At most one `LlmConfig` row SHALL be active at a time.

#### Scenario: Unique credential names

- **WHEN** a client attempts to create a `Credential` whose `name` already exists
- **THEN** the API SHALL return HTTP 409 and SHALL NOT insert a duplicate.

#### Scenario: Activating evicts previous active

- **WHEN** `POST /api/llm-config/{id}/activate` is called with id `B` and id `A` was previously active
- **THEN** in a single transaction `A.is_active` SHALL be set to false and `B.is_active` SHALL be set to true, and the model cache SHALL be invalidated.

### Requirement: Reserved Owner Column

Every persistent table that represents user-owned data (`Workflow`, `Credential`, `LlmConfig`, `Run`) SHALL declare an `owner_id: str | None` column, default `None`, indexed where it would matter for a future multi-user filter.

#### Scenario: Single-user defaults

- **WHEN** any row in `Workflow`, `Credential`, `LlmConfig`, or `Run` is created
- **THEN** `owner_id` SHALL default to `None` and SHALL NOT be required by any API request body.

### Requirement: Workflow Schema Reuse

The `WorkflowVersion.workflow_json` column SHALL store a JSON value that validates against the existing `Workflow` pydantic model from `backend/app/schemas.py` without any structural change to that model.

#### Scenario: Old schema still loads

- **WHEN** a stored `WorkflowVersion` row is read
- **THEN** `Workflow.model_validate(row.workflow_json)` SHALL succeed and the result SHALL be the same shape consumed by the existing executor.

## API contract

| Method | Path | Request | Response | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/workflows` | — | `{items: WorkflowSummary[]}` | id, name, updated_at, last_run_status (nullable) |
| `POST` | `/api/workflows` | `{name, description?}` | `WorkflowDetail` | manual empty workflow |
| `GET` | `/api/workflows/{id}` | — | `WorkflowDetail` | meta + current `Workflow` JSON + chat_session_id |
| `PUT` | `/api/workflows/{id}` | `{name?, description?}` | `WorkflowDetail` | metadata only |
| `DELETE` | `/api/workflows/{id}` | — | `{ok:true}` | cascade delete versions / chat / runs |
| `GET` | `/api/workflows/{id}/versions` | — | `{items: WorkflowVersionSummary[]}` | id, version_number, created_at |

`WorkflowDetail` shape:

```json
{
  "id": "wf_…",
  "name": "Search iPhone on JD",
  "description": "…",
  "current_version_id": "ver_…",
  "version_number": 3,
  "workflow": { "nodes": [...], "edges": [...], "start_id": "n1" },
  "chat_session_id": "cs_…",
  "updated_at": "2026-…",
  "last_run_status": "completed"
}
```

## Data model

```python
class Workflow(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=lambda: f"wf_{uuid4().hex[:10]}")
    name: str
    description: str | None = None
    owner_id: str | None = Field(default=None, index=True)
    current_version_id: str | None = Field(default=None, foreign_key="workflowversion.id")
    created_at: datetime
    updated_at: datetime

class WorkflowVersion(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=...)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    version_number: int
    workflow_json: dict = Field(sa_column=Column(JSON))
    created_at: datetime
    created_by_message_id: str | None = None

class ChatSession(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=...)
    workflow_id: str = Field(foreign_key="workflow.id", index=True, unique=True)
    created_at: datetime

class ChatMessage(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=...)
    session_id: str = Field(foreign_key="chatsession.id", index=True)
    role: Literal["user", "assistant", "system"]
    content: str
    patch_json: dict | None = Field(default=None, sa_column=Column(JSON))
    workflow_version_id: str | None = None
    created_at: datetime

class Run(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=...)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    workflow_version_id: str = Field(foreign_key="workflowversion.id")
    owner_id: str | None = Field(default=None, index=True)
    status: Literal["queued", "running", "completed", "failed", "aborted"] = Field(index=True)
    error: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

class RunEvent(SQLModel, table=True):
    run_id: str = Field(foreign_key="run.id", primary_key=True)
    seq: int = Field(primary_key=True)
    ts: datetime
    event: str
    node_id: str | None = None
    payload_json: dict = Field(sa_column=Column(JSON))

class Credential(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=...)
    name: str = Field(index=True, unique=True)
    kind: Literal["login", "api_key", "token", "other"]
    encrypted_blob: bytes
    hint: str | None = None
    owner_id: str | None = Field(default=None, index=True)
    created_at: datetime
    updated_at: datetime

class LlmConfig(SQLModel, table=True):
    id: str = Field(primary_key=True, default_factory=...)
    provider: Literal["openai", "google"]
    model: str
    encrypted_api_key: bytes
    base_url: str | None = None
    extra_json: dict | None = Field(default=None, sa_column=Column(JSON))
    is_active: bool = Field(default=False, index=True)
    owner_id: str | None = Field(default=None, index=True)
    created_at: datetime
    updated_at: datetime
```

## Out of Scope

- Alembic migrations. Greenfield schema; if future changes alter columns we either rebuild or hand-write an `ALTER TABLE`.
- Cross-process locking (`pysqlite` `journal_mode=WAL` is on, but two FastAPI instances pointing at the same file is undefined behaviour).
- Soft delete / archived state. `DELETE /api/workflows/{id}` hard-deletes with cascade.
- Multi-user filtering. `owner_id` is declared and indexed but never read.
