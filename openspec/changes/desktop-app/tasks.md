## 1. Project scaffold

- [x] 1.1 Create `desktop/` Tauri 2 project with Vite + React, dev proxy to sidecar
- [x] 1.2 Add `frontend/src/desktop/` entry and route shell (login, layout, nav)
- [x] 1.3 Document desktop dev workflow in `desktop/README.md`

## 2. Runtime sidecar

- [x] 2.1 Add sidecar daemon mode: long-lived process with `127.0.0.1:3921` health + status routes
- [x] 2.2 Refactor `app/worker/cli.py` to support `serve` subcommand (or separate `app/worker/daemon.py`)
- [x] 2.3 Bundle sidecar binary per OS into Tauri resources (reuse PyInstaller spec)
- [x] 2.4 Tauri: spawn/stop sidecar on app lifecycle; poll health with splash screen

## 3. Admin authorization (enterprise gate)

- [x] 3.1 Add `Organization.desktop_client_policy` and `Worker.approval_status` (+ approved_at, approved_by) schema migration
- [x] 3.2 API: `POST /workers/{id}/approve`, `POST /workers/{id}/reject`, extend login/connect responses with approval_status
- [x] 3.3 Enforce gate in dispatcher, publish, and sidecar `POST /runs` when pending/rejected
- [x] 3.4 Web WorkersPanel: pending badge, Approve/Reject buttons (admin/owner only); org policy in Settings
- [x] 3.5 Desktop pending screen + poll until approved

## 4. App shell

- [x] 4.1 Login/logout UI with session persistence (worker + web tokens)
- [x] 4.2 Connection status + environment preflight on Overview
- [x] 4.3 System tray (Tauri mode — hide on close, Show/Quit menu)
- [x] 4.4 Settings page (worker profile + local LLM)

## 5. Worker auto-connect

- [x] 5.1 Sidecar opens `WSS /api/v1/workers/connect` on login (reuse `WorkerRuntime`)
- [x] 5.2 Verify machine appears online in cloud Workers UI within 10s (pending or approved per policy) — **manual E2E** documented in `desktop/README.md`
- [x] 5.3 Logout closes WebSocket and clears credentials (`DELETE /session` restarts WS loop; UI clears localStorage)

## 6. Run console (D2)

- [x] 6.1 Localhost API: `POST /runs` start, `GET /runs/:id/events` SSE, `POST /runs/:id/abort`, `GET /runs` list
- [x] 6.2 Desktop `RunConsole` page: active run, event log, abort button
- [x] 6.3 Integrate `LiveStreamPanel` for local runs (sidecar `WS /ws/stream/{id}`)
- [x] 6.4 Local run history list (JSON index under `~/.auto-agent-worker/runs/`)

## 7. Local LLM (D4 partial — can parallel after D2)

- [x] 7.1 Settings UI: provider, model, API key / Vertex fields
- [x] 7.2 Secure local storage — Fernet encryption at `~/.auto-agent-worker/llm.json` with machine-local key in `~/.auto-agent-worker/.key` (sidecar); Tauri keychain deferred (documented in `desktop/README.md`)
- [x] 7.3 Sidecar: skip `install_llm_proxy` in desktop mode; wire `model.py` from local config via `apply_local_config`
- [x] 7.4 Fail fast when LLM nodes run without configuration (`require_configured`)

## 8. Authoring UI (D3)

- [x] 8.1 Workflow list page (local drafts + cloud-published indicator)
- [x] 8.2 Embed workflow canvas + inspector (read-only `WorkflowCanvas`; full edit via web fallback link)
- [x] 8.3 Recording pages in desktop routes (`RecordingsListPage`, `RecordingDetailPage` at `/recordings`, `/recordings/:id`)
- [x] 8.4 Autonomous task launcher page (`/tasks/new`, reuses `AutonomousTaskPage` → cloud `/api/tasks`)

## 9. Workflow sync (D4)

- [x] 9.1 Local draft store (JSON files: `workflow_id`, `local_id`, `draft_json`, `cloud_version_id`, timestamps)
- [x] 9.2 Publish: upload draft → cloud `POST /api/workflows/{id}/versions` (403 if not approved)
- [x] 9.3 Pull: download latest published via `POST /cloud/workflows/{id}/pull`
- [x] 9.4 Offline edit: queue publish intent in `~/.auto-agent-worker/publish_queue.json`; retry on sidecar startup; **Queued for publish** badge on drafts

## 10. Packaging & CI (D5)

- [x] 10.1 Tauri build matrix: macOS (.dmg), Windows (.exe/.msi), Linux (AppImage/deb) — documented in `desktop/README.md`
- [x] 10.2 GitHub Actions workflow `.github/workflows/build-desktop.yml` (macOS / Windows / Linux matrix)
- [x] 10.3 Update root README: desktop as primary onboarding; demote web+CLI path
- [x] 10.4 macOS codesign/notarize — `desktop/scripts/codesign-macos.sh` stub + env vars in `desktop/README.md`

## 11. Verification

- [x] 11.1 E2E: login → pending → admin approves → app unlocks — **API integration** (`test_desktop_e2e.py` publish gate); full UI flow **manual** in `desktop/README.md`
- [x] 11.2 E2E: pending device cannot run or publish; rejected device shows denied state — **automated** (`test_daemon.py` 403, `test_workers.py`)
- [x] 11.3 E2E: approved device → run locally → log + livestream — **automated** run start (`test_daemon.py`); livestream **manual** in README
- [x] 11.4 E2E: edit draft offline → Publish after approval → cloud trigger dispatches — **automated** publish queue + flush (`test_desktop_e2e.py`, `test_daemon.py`)
- [x] 11.5 Regression: CLI worker subject to same approval gate; `open` policy auto-approves for dev — **covered by `test_workers.py`**
