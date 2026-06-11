## ADDED Requirements

### Requirement: Persisted Run Lifecycle

The `Run.status` enum SHALL be exactly `queued | running | completed | failed | aborted`. A `Run` row SHALL be created in `queued` state by `POST /api/runs` and SHALL transition through the lifecycle:

```
queued ──► running ──► completed | failed | aborted
   │
   └────────────────► aborted   (cancelled before pickup)
```

The transitions `running → aborted` (in-flight cancel) and `queued → aborted` (cancel before pickup) are both legal terminal paths; every other transition is forbidden.

#### Scenario: Queued row from POST /api/runs

- **WHEN** the frontend calls `POST /api/runs { workflow_id }`
- **THEN** the server SHALL insert a `Run` with `status="queued"`, `workflow_version_id=workflow.current_version_id`, `queued_at=now()`, `started_at=null`, and return `{run_id, status: "queued"}`.

#### Scenario: Single active run per workflow, queued otherwise

- **WHEN** a `POST /api/runs` arrives while another run for any workflow is already `running`
- **THEN** the new row SHALL remain `status="queued"` until the scheduler promotes it; the server SHALL NOT reject the request with HTTP 409, and the queued row SHALL be visible in `GET /api/runs` immediately.

#### Scenario: Running transition on scheduler pickup

- **WHEN** the queue scheduler promotes a queued run (no other `running` run exists) and the WebSocket `/ws/run` for that `run_id` is open
- **THEN** the server SHALL set `status="running"`, `started_at=now()`, and proceed to execute; if the addressed run is already `running` / terminal the server SHALL emit `run_failed` and close.

#### Scenario: Terminal transition writes finished_at

- **WHEN** the executor emits `run_completed`, `run_failed`, or `run_aborted`
- **THEN** `Run.status` SHALL be set to the matching terminal value, `finished_at` SHALL be set to the emit time, and (for failures) `Run.error` SHALL be set to the event's `error` string.

#### Scenario: Aborted on disconnect

- **WHEN** the WebSocket closes for a persisted run without a terminal event having been written
- **THEN** the server SHALL set `Run.status="aborted"` and `finished_at=now()`.

#### Scenario: Aborted from the queue before pickup

- **WHEN** the user sends an abort frame (or calls `POST /api/runs/{id}/abort`) for a run whose `status="queued"`
- **THEN** the server SHALL transition the row directly to `status="aborted"`, set `finished_at=now()`, persist a `run_aborted` event with `seq=0`, and the scheduler SHALL NOT promote the row.

### Requirement: Abort Frame On WebSocket

The `/ws/run` socket SHALL accept a `{type:"abort", run_id?: str}` client frame. On receipt the executor SHALL set a cancel flag, the current node SHALL attempt cleanup (cancel pending Playwright actions), and the run SHALL terminate with `status="aborted"`. A `run_aborted` event SHALL be emitted exactly once and persisted as a `RunEvent`.

#### Scenario: Abort cancels the current node

- **WHEN** the executor is executing node `n3` and the client sends `{type:"abort", run_id}`
- **THEN** within best-effort cleanup latency the executor SHALL stop after `n3`, MUST NOT advance to `n4`, MUST emit `run_aborted`, and the run SHALL end with `status="aborted"`.

#### Scenario: Abort without run_id targets the socket's run

- **WHEN** the client sends `{type:"abort"}` (no `run_id`) over a socket bound to `run_X`
- **THEN** the server SHALL treat it as `{type:"abort", run_id:"run_X"}`.

### Requirement: Verbatim Event Persistence

For runs initiated with a `run_id`, every event emitted over `/ws/run` SHALL ALSO be persisted as a `RunEvent` row in the order emitted. The persisted `payload_json` SHALL equal the JSON object that was sent over the wire.

#### Scenario: Linear six-node sample

- **WHEN** the sample workflow runs as a persisted run
- **THEN** `RunEvent` rows for that run SHALL be: one `run_started`, six pairs of `(node_started, node_completed)`, one `run_completed` — in that order, with `seq` 0..N monotonically — and the bytes of each `payload_json` SHALL equal the corresponding WS frame.

#### Scenario: Persistence failure does not break stream

- **WHEN** a `RunEvent` insert raises (e.g. transient DB lock)
- **THEN** the WebSocket SHALL continue forwarding events to the client, the executor SHALL NOT stop, and the failure SHALL be logged; subsequent events SHALL still be attempted.

### Requirement: Run List Endpoint

`GET /api/runs` SHALL return the N most recent runs (default N=50) optionally filtered by `workflow_id`, ordered by `created_at` descending. Each item SHALL include enough to render the runs page without further requests.

#### Scenario: List shape

- **WHEN** the runs page mounts and calls `GET /api/runs`
- **THEN** each returned item SHALL have shape `{id, workflow_id, workflow_name, version_number, status, started_at, ended_at, duration_ms, error_summary}` where `error_summary` is the first 200 chars of `Run.error` for failed runs.

#### Scenario: Filter by workflow

- **WHEN** `GET /api/runs?workflow_id=wf_abc` is called
- **THEN** only runs whose `workflow_id == "wf_abc"` SHALL be returned.

### Requirement: Run Replay Endpoint

`GET /api/runs/{id}` SHALL return everything needed to replay the run on the canvas: the run metadata, the workflow version JSON used, and the full ordered event list.

#### Scenario: Replay payload

- **WHEN** the frontend calls `GET /api/runs/{id}` for a completed run
- **THEN** the response SHALL be `{run, workflow_version: {id, version_number, workflow_json}, events: RunEvent[]}` where `events` is ordered by `seq` and the JSON shape of each event matches the live `/ws/run` frame contract.

### Requirement: Frontend Replay Player

The frontend SHALL provide a replay UI that loads `/api/runs/{id}`, renders the workflow on the same `WorkflowCanvas` used by live runs, and dispatches each `RunEvent.payload_json` into the existing `applyEvent(...)` store action in order.

#### Scenario: Replay drives glow

- **WHEN** the replay player runs a completed past run
- **THEN** the canvas SHALL show the same glow sequence the live run did, in the same order, ending with all nodes in their final state.

#### Scenario: Wait nodes do not replay their delay

- **WHEN** a past run contains a `wait` node that took 5000 ms
- **THEN** the replay player SHALL NOT recreate the 5000 ms delay; events SHALL be dispatched at the player's chosen pacing (instant, 1×, 2×).

#### Scenario: Replay player has at least three speeds

- **WHEN** the user opens the replay page
- **THEN** controls SHALL be visible for at least: instant (all events at once), 1× (preserve original inter-event intervals as best-effort, capped at 2 s/event), and 2× (half intervals, same cap).

### Requirement: Run-Now Button On Workflow Detail

The workflow detail page SHALL expose a "Run Now" button that orchestrates a persisted run: `POST /api/runs { workflow_id }` → open `/ws/run` with `run_id` → drive the canvas and run log via the same store action used today. When the run finishes the page SHALL link the user to `/runs/{id}` so they can replay or revisit it.

#### Scenario: Run Now happy path

- **WHEN** the user clicks "Run Now" on a workflow detail page
- **THEN** the frontend SHALL call `POST /api/runs`, open `/ws/run` with `{type:"start", run_id}`, render live events on the canvas and run log, and on `run_completed` display a link to the run-detail page.

#### Scenario: Concurrent run is queued, not rejected

- **WHEN** a run is already `running` on the backend and the user clicks "Run Now" on the same or a different workflow
- **THEN** the backend SHALL create a new `Run` row with `status="queued"` and return HTTP 200; the UI SHALL display the run's queue position alongside its `queued_at` timestamp and a "停止" button that aborts the queued row before pickup.

## API contract

| Method | Path | Request | Response | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/api/runs` | `{workflow_id, version_id?}` | `{run_id, status:"queued"}` | always enqueues; never returns 409 |
| `GET` | `/api/runs` | `?workflow_id=&limit=` | `{items: RunSummary[]}` | list (incl. queued), default limit 50 |
| `GET` | `/api/runs/{id}` | — | `RunDetail` | metadata + version + events |
| `POST` | `/api/runs/{id}/abort` | — | `RunOut` | sets cancel flag; transitions to `aborted` (works for queued and running rows) |
| `WS` | `/ws/run` | `{type:"start", run_id}` \| `{type:"start", workflow}` \| `{type:"abort", run_id?}` | event frames | persisted variant when `run_id` given; abort frame triggers `run_aborted` |

`RunSummary`:

```json
{
  "id": "run_…",
  "workflow_id": "wf_…",
  "workflow_name": "Search iPhone on JD",
  "version_number": 3,
  "status": "completed",
  "started_at": "2026-…",
  "ended_at": "2026-…",
  "duration_ms": 9821,
  "error_summary": null
}
```

`RunDetail`:

```json
{
  "run": { ...RunSummary, "error": "<full text or null>" },
  "workflow_version": {
    "id": "ver_…",
    "version_number": 3,
    "workflow_json": { "nodes":[...], "edges":[...], "start_id":"n1" }
  },
  "events": [
    {"seq": 0, "ts": "2026-…", "event": "run_started", "node_id": null, "payload_json": {...}},
    ...
  ]
}
```

## Data model

See `workflow-persistence` for `Run` and `RunEvent`. Indexes added by this spec:

- `Run`: composite index `(workflow_id, queued_at DESC)` for the list page; index on `status` for the FIFO scheduler's pickup query.
- `RunEvent`: index `(run_id, seq)` for replay; range scan from there.

### Run queue model

The queue is **not** a separate table. Rows with `status="queued"` ARE the queue, ordered by `queued_at ASC` and partitioned by `workflow_id`. The scheduler advances by selecting `WHERE status="queued" ORDER BY queued_at ASC LIMIT 1` whenever the global "running" slot is free; a process-wide `asyncio.Lock` guarantees at most one row holds `status="running"` across the whole backend.

## Out of Scope

- Cross-workflow priority queues (the queue is strictly FIFO).
- Run sharing / export. The DB row is the only sharing surface.
- Replay of fuzzy-action screenshots taken during the original run (we don't store them).
- Retention policy / auto-pruning. All runs are kept until the user deletes the workflow.
