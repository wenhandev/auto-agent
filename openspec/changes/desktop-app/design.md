## Context

`auto_agent` shipped a full-featured **web** workflow editor, cloud backend, and a **CLI worker** (`auto-agent-worker`) for edge execution. The local-runtime-worker change correctly split cloud orchestration from edge Playwright execution, but the **product surface** remained web-first with worker as an add-on.

User research in this thread converged on:

- **App-first**: one installable desktop product, not "open browser + run worker.exe".
- **PAD-like scope**: design, record, run, debug in the app.
- **Hybrid sync (C)**: local drafts offline-capable; **Publish** to cloud for team + triggers.
- **Local secrets**: LLM keys and credential vault on device.
- **Platforms**: macOS, Windows, Linux (Tauri + existing PyInstaller runtime binary per OS).

Prior art: Power Automate Desktop (primary desktop + cloud sync), UiPath Assistant, not n8n Cloud (web-only).

## Goals / Non-Goals

**Goals:**

- Ship a **Desktop App** as the default user-facing product.
- Embed existing Python executor (`WorkerRuntime`, `runtime_engine`, Playwright) — no rewrite to Rust/JS.
- Reuse existing React UI (canvas, recording, run replay) inside Tauri WebView.
- Support **local draft → Publish → cloud trigger → dispatch back to desktop** loop.
- Configure LLM on device; desktop-initiated runs do not require cloud LLM proxy.
- Maintain outbound worker WebSocket so cloud cron/webhooks can assign runs to online desktops.
- macOS, Windows, Linux installers from CI.

**Non-Goals:**

- React Native or mobile v1.
- Replacing cloud backend; web UI stays as admin/companion.
- Real-time collaborative editing (Google Docs style).
- Cross-machine browser profile / credential sync.
- Offline execution of cloud-queued runs when app is not running.
- Rewriting executor in non-Python languages.

## Decisions

### Decision 1: Tauri 2 + React (not Electron, not React Native)

- **Why**: small binaries, native tray/window on three OSes, WebView hosts existing React. Team already has React + Vite in `frontend/`.
- **Rejected Electron**: larger footprint; no strong advantage given React reuse.
- **Rejected React Native**: poor fit for `@xyflow/react`, Playwright sidecar, desktop automation UX.

### Decision 2: Python runtime as bundled sidecar subprocess

```
Tauri (Rust) ──spawn──► auto-agent-runtime (PyInstaller onedir)
                              │
                              ├── localhost:3921 HTTP API
                              ├── WorkerRuntime + executor
                              └── Playwright Chromium
```

- **Why**: zero rewrite of executor; same code path as CLI worker today.
- **API surface**: health, login state, start/stop run, run events SSE/WS, settings (LLM, tags), preflight.
- **Rejected in-process Python embedding**: fragile across OSes; subprocess isolation matches Playwright crash containment.

### Decision 3: UI code sharing strategy

Phase 1: Vite multi-page — `frontend/` builds `desktop` entry importing shared `components/`, `lib/`, `types-platform.ts`.

Phase 2 (optional): extract `packages/ui` when web/desktop divergence hurts.

- **Why**: fastest path; avoid big-bang monorepo refactor.
- **Desktop routes**: `/`, `/workflows`, `/workflows/:id`, `/record`, `/runs`, `/settings` (subset of web routes).

### Decision 4: Hybrid workflow lifecycle (model C)

| State | Location | Visible to team |
|-------|----------|-----------------|
| Local draft | Device SQLite + JSON files | No |
| Published version | Cloud `WorkflowVersion` | Yes |
| Local run (unpublished test) | Device run store + optional cloud upload | Optional |

- **Publish**: POST draft to cloud → new version; marks `published_at`, `cloud_version_id` locally.
- **Pull**: fetch latest published version; overwrite local draft if user confirms.
- **Run locally**: always allowed on draft; cloud trigger only uses **published** versions.

### Decision 5: Local LLM for desktop-mode runs

- Settings page: `GEMINI_PROVIDER`, project, model, API key or ADC path — stored in OS keychain via Tauri plugin where available, else encrypted file under `~/.auto-agent/`.
- Desktop runtime calls `app.agents.model` directly; **does not** call `install_llm_proxy`.
- Cloud-dispatched runs on desktop also use local LLM (data stays on device).
- Cloud LLM proxy remains for legacy CLI worker and cloud-mode runs.

### Decision 6: Desktop auto-registers as worker

On login, sidecar opens `WSS /api/v1/workers/connect` with same `wk_sess_` token as CLI worker today.

- **Why**: cloud triggers and "Run on worker" from web still work; one machine, one agent.
- **Display**: app shows "Connected to cloud" + worker row metadata; no separate worker install.

### Decision 7: Admin authorization before use (enterprise gate)

Desktop clients SHALL NOT execute or publish until an org admin approves the device.

**Org policy** (`Organization.desktop_client_policy`):

| Value | Behavior |
|-------|----------|
| `disabled` | No desktop/CLI worker login |
| `approval_required` | Login OK → `Worker.approval_status=pending` → admin Approve → full use (**default**) |
| `open` | Auto-approve on login (dev / small teams) |

**Flow:**

```
User installs App → login (valid user/password)
       ↓
Cloud upserts Worker (pending) + issues wk_sess_
       ↓
App: 「等待管理员授权」 screen (poll GET /workers/me or status in login response)
Web: Admin sees pending row → Approve / Reject
       ↓
Approved → App unlocks → runs, publish, cloud dispatch enabled
```

- **Why**: enterprise admins must control which machines run automations on corp networks; matches MDM / self-hosted runner approval patterns.
- **Rejected**: enrollment-token-only (too much admin friction for initial login); silent auto-approve (no gate).

**Blocked while pending**: cloud dispatch, `POST /runs`, Publish, recording start (browser launch). **Allowed while pending**: login, pending UI, optional local settings read-only.

**Confirmed (product):** `approval_required` is the default for new organizations; admins may switch to `open` for dev/small teams in org Settings.

### Decision 8: Web UI role after desktop

- **Keep** web for: org admin, member management, viewing team run history, trigger configuration, API keys.
- **Deprioritize** for new features: primary authoring path moves to desktop first.
- No removal in v1 — document "Desktop recommended" in README.

## Risks / Trade-offs

- [Two UI targets drift] → shared component imports; desktop-first feature flag; periodic parity checklist.
- [Sidecar startup latency] → splash screen + health poll; keep sidecar warm while app open.
- [PyInstaller bundle size ~200MB+] → document; Chromium still via `install-browsers` on first run.
- [macOS Gatekeeper unsigned builds] → document right-click Open; follow-up codesign/notarize.
- [Offline draft vs cloud Pull conflict] → explicit merge UI deferred; v1: Pull replaces local with confirm dialog.
- [Security of localhost API] → bind 127.0.0.1 only; optional token file readable only by app user.

## Migration Plan

1. **Phase D1**: Tauri shell + sidecar health + login + tray (no editor).
2. **Phase D2**: Embedded run console + local run from workflow ID pulled from cloud.
3. **Phase D3**: Full editor + recording in app; local draft store.
4. **Phase D4**: Publish/Pull sync + local LLM settings.
5. **Phase D5**: CI installers (dmg, exe, AppImage); README onboarding switch to desktop.

Rollback: desktop optional; web + CLI worker unchanged.

## Open Questions

- Monorepo extract `packages/ui` timing — after D3 if import paths become painful.
- Run event upload: always sync to cloud when online, or user toggle for privacy-sensitive runs?
- Auto-update mechanism (Tauri updater vs store) — defer post-v1.
- Re-approval after hardware change (`machine_id` change): treat as new pending device (lean: yes).

**Resolved:** Default `desktop_client_policy=approval_required` for new orgs (user confirmed).
