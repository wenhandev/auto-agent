## Context

The desktop app is Tauri (Rust) + React UI. Execution lives in Python: **local cloud** (FastAPI on `8001`) for auth/workflows/triggers, and **runtime sidecar** (FastAPI on `3921`) for local runs, drafts, and worker WebSocket.

Previously only the sidecar was auto-spawned in debug builds; cloud was a separate manual step.

## Architecture

```
User opens Auto Agent.app
        │
        ▼
  Tauri (Rust parent)
        ├── spawn local cloud  → 127.0.0.1:8001  (uvicorn app.main:app)
        └── spawn sidecar      → 127.0.0.1:3921  (python -m app.worker.daemon)
        │
        ▼
  React RuntimeGate polls /api/health + /health
        │
        ▼
  Login → normal desktop flow
```

## Decisions

### Decision 1: Tauri spawns both children

- **Dev**: `backend/.venv/bin/python` (or `AUTO_AGENT_PYTHON`) runs uvicorn and daemon from source.
- **Release**: if `desktop/src-tauri/binaries/auto-agent-cloud-{triple}` and `auto-agent-runtime-{triple}` exist, spawn those; otherwise skip (future packaging step).
- Logs: `/tmp/auto-agent-cloud.log`, `/tmp/auto-agent-tauri-sidecar.log`.

### Decision 2: UI waits for both endpoints

`RuntimeGate` polls cloud `GET /api/health` and sidecar `GET /health` (optionally sidecar `GET /ready` aggregates cloud reachability). Splash shows "Starting Auto Agent…" without manual-start instructions.

### Decision 3: Release bundling (future)

PyInstaller bundles:

| Binary | Role |
|--------|------|
| `auto-agent-cloud-{triple}` | uvicorn + FastAPI backend |
| `auto-agent-runtime-{triple}` | sidecar daemon (`serve`) |

Copied into `desktop/src-tauri/binaries/` per [Tauri external binaries](https://v2.tauri.app/develop/sidecar/). v1 ships spawn logic + README checklist; full cloud bundle is a follow-up build script.

## Lifecycle

| Event | Action |
|-------|--------|
| App setup | spawn cloud, spawn sidecar |
| Tray Quit / RunEvent::Exit | kill both children |
| Window close | hide to tray (unchanged); children keep running |
