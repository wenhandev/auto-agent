## Why

Phases 1–3 hid localhost from the WebView (Tauri invoke + UDS IPC), but the desktop product still **feels like a web client attached to a Python sidecar**: two OS processes, an internal FastAPI server, developer-facing Overview/preflight copy, and shared web routes (Recordings, Autonomous task). Users expect **one app** — open Auto Agent, sign in, run workflows — without mental model of runtime, sidecar, or ports.

## What Changes

- **Phase 4A (product shell)**: Desktop-first navigation and copy — Home as default landing, user-facing device status, production login without cloud URL / worker jargon, sidebar status instead of yellow “starting services” banners when possible.
- **Phase 4B (embedded runtime IPC)**: Replace the Python FastAPI daemon HTTP surface with **structured Tauri commands** calling Python logic in-process or over a minimal binary IPC channel (no uvicorn, no REST on UDS/TCP for UI paths).
- **Phase 4C (process collapse)**: Long-term option to embed Python in the Tauri process (PyO3 / `libpython`) or a single long-lived worker thread — **one user-visible process** in Activity Monitor.
- Preserve cloud orchestration at `https://rpa.wenhandev.com`; desktop remains an edge executor, not an offline cloud replacement.
- Dev mode keeps source Python + optional TCP for debugging; release builds use embedded path only.

## Capabilities

### New Capabilities

- `embedded-runtime-ipc`: Structured desktop runtime API exposed via Tauri `invoke` (session, runs, drafts, LLM settings, preflight, streams) without WebView HTTP to loopback.
- `desktop-product-shell`: Desktop-specific IA, copy, and startup behavior distinct from the web admin UI.

### Modified Capabilities

- `desktop-app-shell`: Default routes and startup gate behavior — Home-first IA, production startup waits on local runtime only.

## Impact

- `client/src-tauri/` — new command module(s), eventual removal of `runtime_bridge` HTTP relay
- `backend/app/worker/` — split daemon HTTP handlers into callable library functions; daemon optional for dev/CLI
- `frontend/src/client/` — Home page, nav, copy; shrink direct reuse of web-only pages over time
- PyInstaller bundle — may shrink if FastAPI/uvicorn removed from release path
- CI release pipeline — unchanged artifact shape (.dmg); internal architecture changes only
