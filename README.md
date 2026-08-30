# auto-agent — Client-first browser automation

## Primary onboarding: Auto Agent Client

The recommended way to run automations is the **native client app** (Tauri + local runtime sidecar). One install gives you login, workflow viewing, local runs, recordings, autonomous tasks, and encrypted local LLM keys.

**Start here:** [client/README.md](client/README.md)

Download installers from your cloud console at **`/client`** (production: [https://rpa.wenhandev.com/client](https://rpa.wenhandev.com/client)).

Quick dev setup:

```bash
# Terminal 1 — cloud backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8001

# Terminal 2 — client (Tauri + sidecar + UI)
cd client && npm install && npm run tauri:dev
```

Routes in the client shell include **Run console**, **Workflows**, **Recordings**, **Autonomous task** (`/tasks/new`), and **Settings**.

## Web console (Auto Agent)

| Path | Use when |
|------|----------|
| [Web UI](frontend/) (`npm run dev`) | Org admin, worker approval, workflow editor, team settings, **client download** |
| Production | [https://rpa.wenhandev.com](https://rpa.wenhandev.com) — control plane only (no Playwright on server) |

The web console and Auto Agent Client share the same cloud session and approval gates; the browser UI is for administration and design, not day-to-day execution.

## Sidecar build (developers)

PyInstaller scripts in [worker/](worker/README.md) package the Python runtime embedded inside the Client. End users do not install or run a separate CLI worker.

---

## What it is (web demo / legacy POC)

`auto-agent` is a local proof-of-concept that turns a natural-language
description of a browser task (Chinese or English) into a typed `Workflow` JSON
graph, renders it as a glowing flowchart in the browser, and then executes it
node-by-node against a real headed Chromium window. Each node lights up as it
runs, streams progress messages back over a WebSocket, and turns green or red
when it finishes.

Under the hood the planner is a Google ADK `LlmAgent` with
`output_schema=Workflow` (so the model is forced to return strict JSON), and
the "fuzzy" perception step is a second ADK `LlmAgent` driving Playwright
through `FunctionTool`s. The model layer is a single helper
(`backend/app/agents/model.py`) that returns either a Gemini model id or a
`LiteLlm("openai/...")` wrapper depending on `LLM_PROVIDER` in `.env`. The
executor is a custom async graph walker that emits `node_started` /
`node_progress` / `node_completed` / `node_failed` events on `/ws/run`, which
the React + ReactFlow frontend consumes to drive the glow.

## Requirements

- Node.js >= 20.19
- Python >= 3.11
- A one-time `playwright install chromium` to download the browser binary
- (Optional) An `OPENAI_API_KEY` or `GOOGLE_API_KEY` for full LLM mode

The repo ships with a hardcoded sample workflow at `GET /api/sample-workflow`
and a 3-step fuzzy-action stub, so the demo runs end-to-end with **no API key**.

## Quick start (demo mode, no API key)

Open two PowerShell terminals at the repo root.

**Terminal 1 — backend:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -e .
playwright install chromium
uvicorn app.main:app --port 8000 --reload
```

**Terminal 2 — frontend:**

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>, click **「加载示例」** (Load sample), then
**「运行」** (Run). A real Chromium window will pop up on your desktop and
walk through the 6-node sample workflow: navigate → wait → fuzzy_action →
extract → navigate → wait. The fuzzy node `n3` will emit three Chinese
progress messages (`分析页面截图... → 决定下一步动作... → 执行点击...`) because
no LLM key is configured.

## Full mode (with LLM)

Copy the env template and fill in a real key:

```powershell
cd backend
copy .env.example .env
notepad .env
```

Pick a provider in `.env`:

```env
# OpenAI (default)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# OR Google Gemini
# LLM_PROVIDER=google
# GOOGLE_API_KEY=...
# GOOGLE_MODEL=gemini-2.0-flash

BROWSER_HEADLESS=false
FUZZY_MAX_STEPS=5
```

Restart `uvicorn`. In the UI, type a description in the input box and click
**「生成工作流」** (Generate workflow), then **「运行」**.

Example prompt:

> 打开 https://example.com，等待 1 秒，找到 h1 主标题，然后跳转到 https://example.org

The planner will produce a `Workflow` JSON, ReactFlow lays it out top-to-bottom
via `dagre`, and the same `/ws/run` executor drives the real browser. On any
`fuzzy_action` node the second agent will actually call Playwright tools
(`click_text`, `fill_field`, `scroll`, `screenshot`, `done`) and stream each
tool call back as a `node_progress` event.

## Verifying the POC

With the backend running on :8000:

```powershell
# backend venv activated
python scripts\ws_smoke.py
```

Expected: 6 `node_started`, 6 `node_completed`, at least 3 `node_progress`
events on `n3`, and `run_completed`. To verify against a different port,
override `AUTO_AGENT_PORT`:

```powershell
$env:AUTO_AGENT_PORT="8001"
python scripts\ws_smoke.py
```

`scripts\planner_smoke.py` is an optional second check that exercises
`POST /api/workflow/generate`; it skips cleanly when no LLM key is set.

## Architecture

```
┌─────────────────┐    HTTP /api/workflow/generate    ┌─────────────────────┐
│  React + Vite   │ ────────────────────────────────▶ │  FastAPI            │
│  ReactFlow      │ ◀────── Workflow JSON ─────────── │  PlannerAgent (ADK) │
│  dagre layout   │                                   │   LlmAgent + schema │
│  zustand store  │ ─── WS /ws/run (start frame) ───▶ │                     │
│  GlowNode UI    │ ◀── node_started/progress/done ── │  Executor (async)   │
└─────────────────┘                                   │   ├─ deterministic  │
                                                      │   │  actions        │
                                                      │   └─ FuzzyAgent     │
                                                      │      LlmAgent +     │
                                                      │      FunctionTools  │
                                                      └──────────┬──────────┘
                                                                 │ Playwright
                                                                 ▼
                                                       headed Chromium window
```

Key files:

- `backend/app/agents/model.py` — single Plan A model helper (Gemini id or `LiteLlm`).
- `backend/app/agents/planner.py` — ADK `LlmAgent(output_schema=Workflow)`.
- `backend/app/agents/fuzzy.py` — ADK `LlmAgent` + Playwright `FunctionTool`s with keyless 3-step stub fallback.
- `backend/app/executor.py` — async graph walker, emits the WS event stream.
- `backend/app/sample.py` — hardcoded 6-node demo workflow.
- `frontend/src/components/GlowNode.tsx` — the per-node glowing card.
- `frontend/src/components/WorkflowCanvas.tsx` — ReactFlow + dagre layout.
- `frontend/src/store.ts` — zustand store that applies WS events to node state.
- `openspec/changes/auto-agent-mvp/design.md` — full design rationale (Plan A).

## Troubleshooting

**Chromium window doesn't appear.** Make sure `BROWSER_HEADLESS=false` (default)
in `backend/.env`, and that you actually ran `playwright install chromium`.
If a corporate proxy blocked the binary download, the browser launch will
fail at the first `navigate` node and the run will end with `node_failed`.

**`/api/health` returns 404 or the WS smoke test times out.** Another
process is bound to port 8000. Find it with
`netstat -ano | findstr ":8000"`, then either stop it or run
`auto-agent` on a different port:

```powershell
uvicorn app.main:app --port 8001
$env:AUTO_AGENT_PORT="8001"
python scripts\ws_smoke.py
```

The frontend Vite proxy is hardcoded to forward `/api` and `/ws` to
`http://localhost:8000`, so if you change the backend port you'll need to
edit `frontend/vite.config.ts` too (or just keep 8000 free for `auto-agent`).

**Vite picks 5174 / 5175 instead of 5173.** Another dev server already
owns 5173. Either stop it or open the URL Vite prints in the terminal.

**Planner returns HTTP 400 "LLM API key not configured".** You're in demo
mode; click **「加载示例」** instead of **「生成工作流」**, or fill in
`backend/.env` and restart the backend.

**`UnicodeEncodeError` running the smoke script in PowerShell.** Ensure
`$env:PYTHONIOENCODING="utf-8"` is set, or run from a `chcp 65001` shell.
The script already calls `sys.stdout.reconfigure(encoding="utf-8")` so this
is rare on modern Python.

**The fuzzy node finishes too fast / doesn't call the LLM.** Confirm
`OPENAI_API_KEY` (or `GOOGLE_API_KEY`) is set in `backend/.env` and that
the backend was restarted after editing it. Without a key the fuzzy step
falls back to a 3-step simulated trace by design. With a key configured
the stub never runs — failures inside the live ADK loop now propagate
as `node_failed` instead of being silently masked.

**Fuzzy node hits `max_steps_reached`.** The default step budget is
`FUZZY_MAX_STEPS=8` (bumped from 5). When the LLM doesn't call `done`
within the budget the executor still emits `node_completed` but the
output payload reports `{"completed": false, "reason":
"max_steps_reached", "last_observation": ...}` — useful for debugging
without crashing the workflow. Bump `FUZZY_MAX_STEPS` in `backend/.env`
if you need a longer ceiling for harder tasks.

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-or-later). If you run a modified version of this project as a network service, you must make the Corresponding Source of your modified version available to users of that service (see LICENSE section 13).

**WorkerX exception.** The copyright holder grants the Bosch WorkerX project an additional permission (AGPL §7) to use Auto Agent ideas and code under WorkerX’s own license, without AGPL copyleft applying to WorkerX. See [GRANT-WORKERX.md](GRANT-WORKERX.md). This does not relicense Auto Agent for anyone else.
