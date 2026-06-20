# Auto Agent Client

Native desktop shell (Tauri 2 + React) with **mono architecture**: one app launch starts local cloud (`127.0.0.1:8001`) and runtime sidecar (`127.0.0.1:3921`) automatically.

## Why localhost ports (interim)

The desktop UI runs in a Tauri WebView (React). The Python **local cloud** and **runtime sidecar** are separate processes today. They communicate with the UI over HTTP on the loopback interface (`127.0.0.1`) — ports 8001 and 3921 are an interim IPC layer, not something end users should configure.

**Release goal:** bundled PyInstaller binaries started by Tauri; the user never sees port numbers or manual service steps.

**Future:** replace loopback HTTP with Tauri `invoke` / a single parent Python process so the app is a true monolith from the user's perspective.

## Prerequisites

| Tool | Purpose |
|------|---------|
| Node.js 20+ | Vite + React UI |
| Python 3.11+ | Local cloud + runtime sidecar (`backend` venv) |
| Rust toolchain | `cargo`, `rustc` for `tauri dev` / `tauri build` |

Install Rust if missing:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Without Rust you can still run the **browser dev UI** with manually started services (see below).

## Quick start (one click)

```bash
cd client
npm install
npm run tauri:dev
```

Tauri automatically spawns:

- **Local cloud** — `uvicorn app.main:app` on `127.0.0.1:8001` (log: `/tmp/auto-agent-cloud.log`)
- **Runtime sidecar** — `python -m app.worker.daemon` on `127.0.0.1:3921` (log: `/tmp/auto-agent-tauri-sidecar.log`)

The UI shows a splash until both pass health checks, then opens the login screen with cloud URL pre-filled as `http://127.0.0.1:8001`.

Set `AUTO_AGENT_PYTHON` if `python3` is not your backend venv interpreter:

```bash
export AUTO_AGENT_PYTHON=/path/to/backend/.venv/bin/python
npm run tauri:dev
```

## Browser-only dev (no Rust)

If you prefer separate terminals for debugging:

Terminal 1 — local cloud:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Terminal 2 — sidecar:

```bash
cd backend
source .venv/bin/activate
python -m app.worker.daemon
```

Terminal 3 — Vite:

```bash
cd client
npm install
npm run dev
```

Open http://localhost:1420 — login uses your cloud URL (default `http://127.0.0.1:8001`).

## UI routes

| Route | Screen |
|-------|--------|
| `/login` | Cloud URL + email + password → worker + web session |
| `/pending` | Polls `GET /api/v1/workers/me` every 10s until approved |
| `/` | Overview (connection + preflight from sidecar `/status`) |
| `/runs` | **Run console** — pick cloud workflow, run locally, live log + stream |
| `/workflows` | Cloud workflow list, pull local drafts, read-only canvas view |
| `/workflows/:id` | Read-only workflow canvas (cloud) |
| `/drafts/:id` | Read-only local draft canvas |
| `/settings` | Worker profile + local LLM config |
| `/recordings` | Cloud recording sessions (list + start) |
| `/recordings/:id` | Recording detail, stop, synthesize workflow |
| `/tasks/new` | Autonomous task launcher → cloud `/api/tasks` |
| `/runs/:runId` | Cloud run replay (after autonomous task) |

Shared React components live under `frontend/src/`; the client entry is `frontend/src/client/main.tsx`.

## Demo: Run console (manual E2E)

1. Launch the desktop app (`npm run tauri:dev`) — cloud and sidecar start automatically.
2. Sign in with a user that has at least one workflow in the org.
3. In web **Settings → Workers**, approve the desktop device if policy requires it.
4. Desktop **Settings → Local LLM**: set provider/model/API key. Saved encrypted at `~/.auto-agent-worker/llm.json` (Fernet; key in `~/.auto-agent-worker/.key`).
5. Open **Run console**, select a workflow, click **Run locally**.
6. Watch the event log and live browser stream (when headed browser + page is active).
7. Use **Abort** to cancel an in-flight run.

**Worker auto-connect:** After login, the sidecar opens `WSS /api/v1/workers/connect`. Within ~10s the device should appear **online** in cloud Settings → Workers. **Sign out** calls `DELETE /session` on the sidecar, clears localStorage, and restarts the worker WebSocket loop.

Automated coverage: `backend/tests/test_daemon.py`, `test_desktop_e2e.py`, and `test_workers.py`.

## Recordings & autonomous tasks

Both use the **cloud API** with your web session token (same as the web UI):

1. Sign in on the desktop app (login stores worker + web tokens).
2. **Recordings** — sidebar → Recordings → **Start recording**. Sessions run on the cloud worker/browser pool; stop and synthesize from the detail page.
3. **Autonomous task** — sidebar → Autonomous task → fill objective → **Start task**. Redirects to run replay at `/runs/:id`.

Requires an **approved** worker when org policy demands it; recordings/tasks themselves are cloud-scoped (not local sidecar runs).

## Offline publish queue

When cloud is unreachable, **Publish** on a local draft returns `202 queued` and writes `~/.auto-agent-worker/publish_queue.json`. The sidecar retries on startup and via `POST /publish-queue/retry`. Drafts show a **Queued for publish** badge in Workflows.

## Runtime sidecar

The sidecar binds **`127.0.0.1:3921` only** and exposes:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness |
| GET | `/ready` | Sidecar up + local cloud reachable |
| GET | `/status` | `approval_status`, `connected`, preflight |
| POST | `/session` | Persist worker + web session tokens |
| DELETE | `/session` | Logout — clear credentials, restart WS loop |
| GET/PUT | `/settings/llm` | Local LLM config (encrypted `~/.auto-agent-worker/llm.json`) |
| GET | `/cloud/workflows` | Proxy list (uses stored web session) |
| GET | `/cloud/workflows/{id}` | Proxy get workflow |
| POST | `/cloud/workflows/{id}/pull` | Pull cloud workflow into local draft store |
| GET/POST | `/drafts` | Local drafts under `~/.auto-agent-worker/drafts/` |
| POST | `/drafts/{id}/publish` | Publish draft → cloud (403 if not approved; 202 + queue if offline) |
| GET | `/publish-queue` | List queued publish intents |
| POST | `/publish-queue/retry` | Flush publish queue when online |
| GET | `/runs` | Recent local runs index |
| POST | `/runs` | Start local run (`workflow_id` or inline `workflow` JSON); **403** if not approved |
| GET | `/runs/{id}/events` | SSE event stream |
| POST | `/runs/{id}/abort` | Cooperative abort |
| WS | `/ws/stream/{id}` | Live JPEG frames for local runs |

Desktop mode uses **local LLM config** (`apply_local_config`) — it does **not** call `install_llm_proxy`. LLM nodes fail fast with a clear error if settings are missing.

For developer debugging without Tauri, see [worker/README.md](../worker/README.md) (`python -m app.worker.daemon` or PyInstaller sidecar).

## Mono architecture (release bundling)

Production builds embed PyInstaller binaries as Tauri external sidecars:

| Binary | Port | Role |
|--------|------|------|
| `auto-agent-cloud-{target-triple}` | 8001 | Local FastAPI cloud (uvicorn) |
| `auto-agent-runtime-{target-triple}` | 3921 | Runtime sidecar daemon |

Copy the PyInstaller onedir bundle into the client tree (CI and local release builds):

```bash
./worker/build-macos.sh    # or build-linux.sh / build-exe.ps1
./worker/stage-client-sidecar.sh
```

Output: `client/src-tauri/binaries/runtime-{target-triple}/` (gitignored).

## CI & releases (GitHub Actions)

| Workflow | Trigger | Output |
|----------|---------|--------|
| **Build client** (`.github/workflows/build-client.yml`) | Push to `main` / manual | macOS / Windows / Linux installer artifacts (14 days) |
| **Release client** (`.github/workflows/release-client.yml`) | Tag `client-v*` / manual | [GitHub Releases](https://github.com/wenhandev/auto-agent/releases) with `.dmg`, `.msi`, `.AppImage` |

**Publish a release:**

```bash
git tag client-v0.1.0
git push origin client-v0.1.0
```

Or: GitHub → Actions → **Release client** → Run workflow → tag `client-v0.1.0`.

Installers bake in `VITE_CLOUD_URL=https://rpa.wenhandev.com`. After a release, optional: set `VITE_CLIENT_DOWNLOAD_*` in `frontend/.env.production` to direct `/client` buttons at the latest assets.

### Packaging checklist

- [ ] `./worker/build-unix.sh` or platform script — sidecar binary
- [ ] `./worker/stage-client-sidecar.sh` — copy into `client/src-tauri/binaries/runtime-{triple}/`
- [ ] `cd client && npm run tauri build` — platform artifact (.dmg / .msi / AppImage)
- [ ] macOS codesign + notarize (optional): `client/scripts/codesign-macos.sh`
- [x] GitHub Actions: `.github/workflows/build-client.yml` + `release-client.yml` (macOS / Windows / Linux)

## System tray

In Tauri mode, closing the window hides to tray. Tray menu: **Show Window**, **Quit**. Click the tray icon to reopen. **Quit** stops local cloud and sidecar child processes.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_CLOUD_URL` | `http://127.0.0.1:8001` | Pre-filled cloud URL on login screen |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8001` | Vite proxy for `/api` (browser dev) |
| `AUTO_AGENT_PYTHON` | `backend/.venv/bin/python` | Python used by Tauri to spawn cloud + sidecar in dev |
