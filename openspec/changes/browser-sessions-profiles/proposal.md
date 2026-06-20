## depends_on

- `auto-agent-platform` — the single Chromium singleton, the `Run` lifecycle, SQLModel persistence, the FastAPI `lifespan`.
- `per-workflow-credentials` (soft) — profiles are how a logged-in state is reused; credentials seed the first login.

No hard dependency on other in-flight changes. `concurrent-runs-browser-pool` builds on the session manager introduced here.

## Why

Today every run launches a fresh browser context and dies with the run. Anything behind a login must re-authenticate every single time — slow, fragile, and a 2FA trigger magnet. Skyvern solves this with two complementary concepts:

- **Browser sessions** — a *live* browser instance (cookies, storage, page context) that survives across multiple operations for up to 24h, useful for chaining tasks in real time or pausing for human intervention between steps.
- **Browser profiles** — *saved snapshots* of browser state (cookies, auth tokens, local/session storage) that persist indefinitely and are re-attached on later runs to **skip login entirely**.

This change adds both so `auto-agent` can "pick up where the last task left off — no re-login, no repeated setup".

## What Changes

- **Data model**:
  - `BrowserProfile` SQLModel — `id`, `name`, `storage_state_path` (Playwright `storage_state` JSON, encrypted at rest via the Fernet key), `created_at`, `updated_at`, `last_used_at`, reserved `owner_id`.
  - `BrowserSession` SQLModel — `id`, `profile_id` (nullable FK), `status ∈ {live, idle, closed, expired}`, `started_at`, `expires_at` (default +24h), `last_activity_at`. Live sessions are tracked in process memory; the row is the durable index.
- **Session manager** `app/services/browser_sessions.py`: owns a map of `session_id → live Playwright context`, enforces the 24h TTL, idle-evicts, and exposes `acquire(session_id|profile_id|None)` / `release(session_id, keep_alive)`.
- **Run wiring**: `POST /api/runs` accepts optional `browser_session_id` and/or `browser_profile_id`. When a session id is given the run attaches to the existing live context; when a profile id is given a fresh context is seeded from the profile's `storage_state`; when neither, current behaviour (ephemeral context).
- **Profile capture**: `POST /api/browser-profiles/{id}/capture-from-run/{run_id}` (or a "保存为配置档" button at run end) writes the run context's `storage_state()` into the profile, so a successful manual login can be frozen and reused.
- **API**: CRUD `/api/browser-profiles`; `/api/browser-sessions` (create live session, list, get, close); a session keep-alive endpoint.
- **UI**: a "浏览器会话" sidebar page listing live sessions (with countdown to expiry + close button) and saved profiles; the Run-Now dialog gains a "使用会话 / 配置档" selector; run detail shows which session/profile it used.

## Capabilities

### New Capabilities

- `browser-profiles`: the `BrowserProfile` entity, encrypted `storage_state` persistence, CRUD endpoints, capture-from-run, and seeding a run context from a profile.
- `browser-sessions`: the `BrowserSession` entity, the in-process session manager, the 24h TTL + idle eviction, attach-a-run-to-a-session, and the session-management UI.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): `Run` gains `browser_session_id` / `browser_profile_id`; `RunOut` exposes them; the run-list/detail shows the binding.
- `platform-shell` (from `auto-agent-platform`): a new "浏览器会话" sidebar page; the Run-Now dialog gains the session/profile selector.

## Impact

- **Backend**: new service + two models + two routers. The Chromium singleton becomes a managed pool-of-contexts keyed by session id (one shared browser process, N contexts). Encrypted profile blobs reuse the existing Fernet key. New `expires_at` reaper task in the `lifespan`.
- **Frontend**: new sidebar page + run-dialog selector + run-detail binding row.
- **Runtime**: live sessions hold a browser context open between runs (memory cost ~per-context); the TTL + idle eviction bound it. A profile-seeded run pays a one-time `add_cookies` / `storage_state` load (~ms).
- **Migration**: new tables via `create_all`; `Run` columns added via the additive-column convention (default `NULL`). Encrypted profile files live under `backend/data/browser_profiles/` (gitignored).
- **Out of scope**: cross-machine profile sync, profile sharing across users (waits for `owner_id`), headful-vs-headless session negotiation beyond the existing `BROWSER_HEADLESS` flag, fingerprint/proxy per profile (→ `captcha-antibot-proxy`).
