## depends_on

- `auto-agent-platform` — `Run` lifecycle, queue, event persistence, WebSocket fanout, `_drive_run`.
- `public-api-and-auth` — API-key auth pattern for worker authentication.
- `concurrent-runs-browser-pool` — dispatcher slot model; worker runs consume capacity on the **worker machine**, not the cloud process.
- `browser-sessions-profiles` — browser profiles and sessions; in worker mode they live on the edge machine.
- `browser-livestream` — live viewport streaming; extended with a relay path when the browser runs on a worker.
- `per-workflow-credentials` — credential resolution; in worker mode secrets stay on the worker.

Soft synergy with `modern-browser-agent-runtime` (LLM-heavy loops call a cloud proxy), `human-in-the-loop` (approval pause/resume crosses the worker boundary), and `multi-user-orgs` (workers scoped to an org).

## Why

Today the backend is a **monolith control plane + execution plane**: `_drive_run` loads a workflow, launches Playwright in-process, runs the executor, and persists events. That works for a local POC with a headed Chromium window, but **breaks the primary cloud deployment model** where workflows must reach **intranet sites, VPN-only apps, and the user's already-logged-in browser session**. Power Automate Desktop, UiPath Robot, and GitHub self-hosted runners solve this with a **local runtime agent** that connects out to a cloud orchestrator. `auto-agent-platform` explicitly deferred cloud deployment and multi-machine workers; this change closes that gap for the **cloud orchestration + edge execution** path (option C).

## What Changes

- **Split execution modes**: each `Run` carries `execution_mode` (`cloud` | `worker`, default `cloud` for backward compatibility) and optional `worker_id` / `worker_pool` tags. Cloud-mode runs behave as today (in-process Playwright on the server). Worker-mode runs are assigned to a connected local agent.
- **Environment preflight**: worker runs `doctor` checks (Playwright, Chromium smoke test, cloud reachability, headed display) before connect; reports `ready` / `degraded` / `not_ready` to cloud; dispatcher skips not-ready workers.
- **Runtime Worker agent**: installable app where the user logs in, preflight passes, then connects outbound; org sees the machine in Settings → Workers; worker executes jobs locally and uploads events + livestream.
- **Cloud dispatcher rework**: when `execution_mode=worker`, the cloud dispatcher **does not** call `_drive_run` locally; it assigns the run to an online worker with free capacity and pushes a job frame. Slot accounting for worker runs is per-worker, not per cloud browser pool.
- **Event relay**: worker-uploaded events use the same `{event, node_id, seq, ...}` shape; cloud validates monotonic `seq`, persists to `RunEvent`, and fans out to existing `/ws/run` subscribers unchanged.
- **Abort and approval relay**: cloud abort and approval resume signals propagate to the worker over the worker WebSocket; worker sets `abort_event` or resumes parked contexts as today.
- **Local secrets on worker**: browser profiles and credential vault resolution for worker runs happen on the worker machine; cloud stores workflow definitions and run metadata only (credential **references**, not plaintext).
- **Cloud LLM proxy (v1)**: worker calls authenticated cloud endpoints for fuzzy/vision/autonomous LLM steps so API keys stay centralized; worker sends prompts and optional screenshot artifacts, cloud returns model output.
- **Livestream relay**: when a run executes on a worker, CDP screencast frames upload to cloud; the existing `/ws/stream/{run_id}` hub forwards them to viewers (UI unchanged).
- **Worker management UI**: Settings → **Workers** page listing machines connected by logged-in users (hostname, user email, online/offline, tags, active runs, last seen); admins can revoke a worker or mint optional enrollment tokens for headless installs; run enqueue UI selects worker or pool.

## Capabilities

### New Capabilities

- `runtime-worker-registration`: **login-first** worker UX (platform credentials → outbound WebSocket → visible in cloud Workers UI), heartbeat, tags; optional admin enrollment tokens for unattended installs.
- `worker-run-dispatch`: cloud-to-worker job assignment, capacity checks, abort/resume signals, and per-worker concurrency.
- `worker-event-relay`: worker-to-cloud run event upload, seq validation, persistence, and fanout to existing subscribers.
- `worker-livestream-relay`: worker-to-cloud JPEG frame relay into the existing livestream hub.
- `worker-local-runtime`: local Playwright, browser profiles, credential resolution, and artifact staging on the worker with cloud metadata sync.
- `worker-environment-preflight`: local readiness checks (Playwright/Chromium, cloud reachability, display, resources) via `doctor` and heartbeat reporting; cloud dispatch respects `environment_status`.

### Modified Capabilities

- `concurrent-run-dispatcher` (from `concurrent-runs-browser-pool`): cloud dispatcher assigns worker-mode runs to edge agents instead of calling in-process `_drive_run`; cloud browser pool applies only to `execution_mode=cloud`.
- `run-history` (from `auto-agent-platform`): `Run` exposes `execution_mode`, `worker_id`, and worker assignment status; queue position reflects worker capacity when applicable.
- `browser-livestream` (from `browser-livestream`): screencast may originate from a worker relay path, not only in-process CDP.
- `api-key-auth` (from `public-api-and-auth`): worker session tokens (`wk_sess_`) from user login authenticate the worker WebSocket and LLM proxy; optional `wk_enroll_` tokens for admin-provisioned headless workers.
- `user-identity-auth` (from `multi-user-orgs`): shared login endpoint reused by worker app; worker sessions scoped to user + org.

## Impact

- **Backend (cloud)**: new `Worker` / `WorkerConnection` models, worker router + WebSocket hub, dispatcher branch for worker runs, event ingest endpoint, LLM proxy routes, livestream ingest. `services/runs.py` splits cloud orchestration from local execution. Lifespan skips Playwright init when `EXECUTION_BACKEND=control_plane_only` (optional deploy mode).
- **Worker package**: new `worker/` Python package (or `backend/app/worker_cli.py` entry point) reusing `executor`, `browser_pool`, `browser_profiles`, local credential backends.
- **Database**: additive columns on `run` (`execution_mode`, `worker_id`, `worker_assigned_at`); new `worker` table.
- **Frontend**: Workers settings page; run dialog worker/pool selector; run detail worker badge.
- **Deployment**: cloud container runs control plane only (no Chromium required); users install worker on intranet desktops. Default single-machine local dev unchanged (`execution_mode=cloud`, worker optional).
- **Migration**: existing runs and enqueue paths default to `execution_mode=cloud`. No breaking API changes; worker mode is opt-in per run.
- **Out of scope v1**: desktop UIA / Win32 automation; worker auto-update installer (MSI/dmg); multi-region worker routing; offline queue-and-sync when worker disconnects mid-run; cross-worker profile sync.
