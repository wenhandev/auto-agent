## Context

The platform runs one Chromium singleton and one run at a time; each run opens a context that is torn down on completion. Playwright already exposes the two primitives we need: `browser.new_context(storage_state=...)` to seed cookies/storage, and `context.storage_state()` to snapshot them. Skyvern separates *live sessions* (ephemeral, ≤24h, in-memory state) from *profiles* (durable snapshots). We mirror that split because they have different lifetimes and different storage strategies.

## Goals / Non-Goals

**Goals:**
- Reuse authenticated state across runs (profiles) and across operations within a window (sessions).
- A single session manager that both the executor and a future browser pool consume.
- Encryption at rest for profile `storage_state` (it contains auth tokens).

**Non-Goals:**
- Concurrency (the manager is built concurrency-ready, but N-at-a-time scheduling is `concurrent-runs-browser-pool`).
- Per-profile proxy/fingerprint (→ `captcha-antibot-proxy`).
- Cross-machine sync.

## Decisions

### Decision 1: One browser process, many contexts keyed by session id
The singleton becomes `browser`, and `BrowserSessionManager` holds `session_id → BrowserContext`. A run attaches to a context by session id, or gets a fresh context (optionally seeded from a profile), or an anonymous ephemeral context.
- **Why**: contexts are the isolation boundary Playwright recommends; one process keeps memory modest.
- **Alternative rejected**: one browser process per session (heavy); persistent-context-on-disk per profile via `launch_persistent_context` (ties a profile to a running process, harder to snapshot/share).

### Decision 2: Profiles store `storage_state` JSON, encrypted with the Fernet key
On capture, `context.storage_state()` → JSON → Fernet-encrypt → `backend/data/browser_profiles/<id>.enc`. On use, decrypt → pass as `storage_state` to `new_context`.
- **Why**: `storage_state` is the portable, documented snapshot format; reusing the credential-vault Fernet key avoids a second key-management surface.
- **Alternative rejected**: copying the on-disk user-data-dir (large, Chromium-version-fragile, not portable).

### Decision 3: Sessions are in-memory truth, the row is an index
`BrowserSession.status`/`expires_at` are persisted so the UI can list them and the reaper can find expired ones, but the live `BrowserContext` lives only in process memory. On backend restart all sessions are marked `expired` (the context is gone) — matching the "Playwright state does not survive restart" reality already accepted by `human-in-the-loop`.
- **Why**: honest about process-bound state; no false promise of resumable live sessions across restarts.

### Decision 4: 24h TTL + idle eviction
`expires_at = started_at + 24h`; an idle session (no activity for `SESSION_IDLE_MINUTES`, default 30) is closed early. A `lifespan` reaper ticks every minute.
- **Why**: matches Skyvern's 24h cap; bounds memory.

### Decision 5: Profile capture is explicit, never automatic
A profile is updated only by an explicit capture call/button, never silently after every run.
- **Why**: auditability; an automation that corrupts state should not poison the saved profile.

## Risks / Trade-offs

- [Encrypted profile leaks auth tokens if the Fernet key leaks] → same blast radius as the existing credential vault; documented; 0600 file perms.
- [Stale profile: cookies expired server-side] → a profile-seeded run that hits a login wall falls through to normal login (or a `login` node); capture refreshes it.
- [Live session memory growth] → TTL + idle eviction + a configurable max-live-sessions cap (default 5) that rejects new sessions with 429.
- [Restart loses live sessions] → rows marked `expired` on boot; UI shows "已过期（服务重启）".

## Migration Plan

- `create_all` makes `browser_profile` / `browser_session` tables.
- `Run.browser_session_id` / `Run.browser_profile_id` added (additive, default `NULL`).
- New `backend/data/browser_profiles/` dir created in the `lifespan` (gitignored).
- New settings: `SESSION_IDLE_MINUTES=30`, `MAX_LIVE_SESSIONS=5`.

## Open Questions

- Should a `vision_navigate`/`login` run auto-prompt "save as profile?" on success? (Lean: surface a button, no auto-prompt.)
- Profile versioning (keep last N snapshots for rollback)? (Defer.)
