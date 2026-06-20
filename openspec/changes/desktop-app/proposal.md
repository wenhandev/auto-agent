## depends_on

- `local-runtime-worker` — outbound WebSocket, `WorkerRuntime`, event relay, preflight (execution engine reused inside the desktop app).
- `record-and-generate` — recording session + workflow synthesis (UI and APIs embedded in the app).
- `browser-sessions-profiles`, `browser-livestream` — local browser sessions and live preview in the app.
- `multi-user-orgs`, `public-api-and-auth` — login, org scoping, cloud sync.
- `autonomous-task-mode` — autonomous runs launched from the app (soft).

## Why

The product today presents as **web UI + optional CLI worker**: users design in the browser, install a separate worker binary, and LLM keys live on the cloud. That split matches a transitional architecture, not the intended product. Users expect a **single installable desktop application** (Power Automate Desktop / UiPath Assistant model): design, record, run, and debug automations locally; cloud provides account, backup, team sharing, and scheduled triggers — not the primary daily interface.

The chosen product model is **hybrid (C)**: workflows can be edited offline as local drafts on the device; **Publish** promotes a version to the cloud as the org-visible source of truth; cloud triggers and peer machines pull published workflows. Sensitive data (LLM keys, browser profiles, credential vault) stays on the desktop.

## What Changes

- **Primary deliverable becomes Desktop App** (Tauri + React UI + embedded Python runtime), not `auto-agent-worker` CLI + web. CLI worker remains for headless/CI only.
- **App shell**: login, connection status, system tray, settings, environment preflight — all in a native window (macOS, Windows, Linux).
- **Embedded local runtime**: existing `WorkerRuntime` / executor runs as a managed subprocess; app UI talks to it via localhost IPC (HTTP or Tauri commands).
- **Local LLM**: Gemini/Vertex/API keys configured in app settings; agent steps call models directly from the device (no cloud LLM proxy for desktop-mode runs).
- **Workflow lifecycle**: local SQLite (or file) store for drafts; **Publish** / **Pull** sync with cloud workflow versions; conflict policy documented (cloud wins on Pull unless local-only draft).
- **Authoring in app**: reuse existing React workflow canvas, node inspector, recording UI, and autonomous task launcher inside the desktop shell (not a separate browser tab).
- **Run console in app**: current run, live log, livestream preview, local run history filtered to this machine; optional upload of run metadata/events to cloud when online.
- **Cloud thins to control plane**: auth, org, published workflows, triggers/cron dispatch to online desktop agents, cross-user run history for published runs. Web UI demoted to admin/read-only companion (not removed in v1).
- **Auto worker registration**: when logged in, the desktop app automatically maintains the outbound worker WebSocket so cloud triggers can reach this machine without a separate worker install.
- **Admin authorization gate**: org admins control desktop client usage via org policy (`disabled` / `approval_required` / `open`) and per-device **Approve / Reject** in Settings → Workers. New devices default to **pending** until approved; execution and Publish are blocked until then.

## Capabilities

### New Capabilities

- `desktop-client-authorization`: org-level desktop policy, per-device `approval_status`, admin approve/reject APIs and UI, pending screen in desktop app, dispatch/run blocked until approved.
- `desktop-app-shell`: Tauri application lifecycle, main window, system tray, login/logout UI, connection indicator, cross-platform installers.
- `desktop-local-runtime`: embedded Python runtime subprocess, localhost control API, start/stop runs locally, bridge to existing executor and Playwright.
- `desktop-local-llm`: on-device LLM provider configuration, secure storage, direct model calls for graph/autonomous/recording synthesis steps.
- `desktop-workflow-sync`: local draft storage, Publish/Pull with cloud workflow versions, offline edit with sync on reconnect.
- `desktop-authoring-ui`: workflow list/editor, recording, and autonomous task entry points hosted inside the desktop app (shared React components).
- `desktop-run-console`: in-app run history (local + synced), live event log, livestream panel, debug/replay for runs on this device.

### Modified Capabilities

- `runtime-worker-registration`: desktop app is the primary worker registration path; CLI worker documented as headless variant sharing the same session format.
- `worker-local-runtime`: runs may be **app-initiated** (user clicks Run in desktop) or **cloud-dispatched** (trigger/worker queue); both use the same embedded runtime.
- `worker-environment-preflight`: preflight results surfaced in app Settings/Overview, not only CLI `doctor`.

## Impact

- **New package**: `desktop/` — Tauri project (Rust shell + Vite React UI entry). May extract shared UI to `packages/ui` or import from `frontend/` with build aliases.
- **Backend (cloud)**: workflow sync API extensions; `Organization.desktop_client_policy`; `Worker.approval_status` + approve/reject endpoints; dispatcher and publish gates for non-approved workers.
- **Frontend (web admin)**: Workers panel — pending badge, Approve/Reject actions, org policy setting for admins.
- **Backend (local sidecar)**: refactor `app/worker/` into a long-lived daemon mode with localhost HTTP API (`127.0.0.1:3921`) controllable by Tauri; keep PyInstaller bundles for runtime binary inside app resources.
- **Frontend**: dual targets — web (admin) and desktop (primary); shared components for canvas, recording, run panels.
- **Worker CLI / PyInstaller**: remain for CI/headless; README positions them as advanced, not default onboarding.
- **Migration**: existing web-first users continue on web; new onboarding points to desktop download. No breaking cloud API changes in v1.
- **Out of scope v1**: React Native mobile app; Win32/macOS UIA desktop automation; auto-update installer (MSI/dmg/store); full offline cloud trigger execution when app is quit; cross-device browser profile sync.
