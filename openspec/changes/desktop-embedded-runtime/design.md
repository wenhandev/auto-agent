## Context

**Today (after Phase 3):**

```
WebView (React)
    │ Tauri invoke
    ▼
Rust runtime_bridge ──HTTP/UDS──► Python auto-agent-worker
                                      ├── uvicorn + FastAPI (daemon.py)
                                      ├── WorkerRuntime + Playwright
                                      └── ~/.auto-agent-worker/ data
    │ HTTPS
    ▼
Cloud (rpa.wenhandev.com)
```

The WebView never calls `localhost:3921` directly, but Python still runs a full HTTP server. Users see sidecar terminology, preflight IDs, and web-parity navigation.

**Constraints:**

- Keep Python executor (`WorkerRuntime`, Playwright, browser pool) — no Rust rewrite.
- macOS / Windows / Linux via Tauri 2.
- Production uses remote cloud only; no bundled local cloud in release.
- PyInstaller sidecar remains acceptable as an interim subprocess until embed path is proven.

## Goals / Non-Goals

**Goals:**

- **Feel like one app**: default Home, friendly status, no ports/services in user copy.
- **Eliminate HTTP IPC for UI** in release: Tauri commands ↔ Python via structured messages.
- **Incremental migration**: port one domain at a time (health → session → runs → streams).
- **Keep dev ergonomics**: `tauri dev` may still spawn TCP daemon until commands cover all paths.

**Non-Goals:**

- Removing Python subprocess in v1 of this change (embed is Phase 4C follow-up).
- Replacing cloud backend or making desktop fully offline.
- Rewriting web UI; desktop may fork routes/components where UX diverges.
- macOS notarization / auto-update (separate track).

## Decisions

### Decision 1: Three sub-phases (4A / 4B / 4C)

| Phase | Focus | User-visible outcome |
|-------|--------|----------------------|
| **4A** | Product shell | Home-first, friendly copy, faster startup UX |
| **4B** | Command IPC | No internal HTTP for UI; Rust calls Python API |
| **4C** | Single process | Optional PyO3 embed; one PID in Task Manager |

**Why:** 4A ships quickly while 4B is the architectural mono milestone; 4C is optional optimization.

**Alternative rejected:** jump straight to PyO3 embed — high risk, blocks Playwright subprocess model and cross-platform packaging.

### Decision 2: Phase 4B IPC — “Python library + thin host” over HTTP

Extract logic from `daemon.py` route handlers into `app.worker.desktop_api` (async functions returning typed dicts/Pydantic models). Two host options:

**Option B1 (recommended v1):** Keep PyInstaller subprocess, replace uvicorn with a **stdin/stdout JSON-RPC loop** or **Unix socket length-prefixed messages** (not HTTP). Rust `runtime_bridge` speaks message frames; Python host dispatches to `desktop_api`.

**Option B2:** PyO3 extension module loaded in Tauri — Python runs in-process on a dedicated thread with GIL management; Playwright still subprocess.

Start with **B1** (minimal change to Playwright isolation); prototype **B2** only if B1 still feels “two apps” in UX testing.

**Alternative rejected:** keep FastAPI on UDS forever — works technically but perpetuates sidecar mental model and HTTP overhead.

### Decision 3: Streaming (SSE / WS) → Tauri events only

Run event and JPEG stream relays already use Tauri events (Phase 2). Phase 4B removes the Python SSE/WS endpoints for UI; Python pushes frames/events into the message channel; Rust re-emits `runtime-run-event` / `runtime-stream-frame`.

**Alternative rejected:** WebView EventSource/WebSocket to loopback — already eliminated in Phase 2.

### Decision 4: Phase 4A desktop IA

| Web-first (today) | Desktop-first (target) |
|-------------------|------------------------|
| Overview (preflight dump) | **Home** — quick actions + status summary |
| Run console | **Runs** |
| Autonomous task / Recordings | Advanced (sidebar lower) or web-only link |
| Settings (worker jargon) | **Settings** — profile, LLM, **Device status** |

Default route `/` → Home. Move technical Overview to `/device` (linked from Settings).

### Decision 5: CLI worker unchanged

`auto-agent-worker doctor|login|serve` remains for developers; `serve` HTTP mode becomes dev-only. Release `.app` does not expose CLI to end users.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| JSON-RPC protocol drift | Version field in envelope; contract tests Rust ↔ Python |
| Long-running Playwright blocks message loop | Python host uses asyncio; heavy work on existing task model |
| Dual code paths during migration | Feature flag `DESKTOP_COMMAND_IPC=1`; fallback to HTTP bridge until parity |
| PyO3 embed crashes take down UI | Defer to 4C; keep subprocess for Playwright crash containment in 4B |
| Larger refactor of daemon.py | Extract handlers incrementally; HTTP routes call same `desktop_api` during transition |

## Migration Plan

1. **4A (now):** Home page, nav, copy, startup gate — no Rust/Python IPC change.
2. **4B.1:** Define message schema; implement `runtime_health`, `runtime_status`, `session_save` over channel.
3. **4B.2:** Runs CRUD + abort; event stream over channel → Tauri events.
4. **4B.3:** Drafts, LLM settings, cloud proxy helpers; remove HTTP invoke from frontend.
5. **4B.4:** Delete uvicorn from release spawn; worker entry `desktop-host` instead of `serve`.
6. **4C (optional):** Evaluate PyO3 vs subprocess after 4B stable.

Rollback: keep HTTP `serve` behind cfg flag until 4B.4 verified on all platforms.

## Open Questions

- Windows UDS vs named pipe for message channel (hyperlocal is unix-only today).
- Whether Recordings / Autonomous task stay in desktop v1 or deep-link to web.
- Bundle size impact of dropping FastAPI/uvicorn from release worker.
