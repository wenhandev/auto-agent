## 1. POC scaffolding (front-loaded, parent worker)

- [x] 1.1 Create `auto-agent/backend/` and `auto-agent/frontend/` directories.
- [x] 1.2 Write `backend/app/schemas.py` (`Workflow`, `Node`, `Edge`, `NodeType`).
- [x] 1.3 Write `frontend/src/types.ts` with TS types that mirror `schemas.py` exactly.
- [x] 1.4 Lock the LLM design at "ADK built-ins only" (no `app/llm/` directory).

## 2. Backend POC (parallel sibling A)

- [x] 2.1 Write `pyproject.toml` with deps: `fastapi`, `uvicorn[standard]`, `playwright`, `pydantic>=2`, `pydantic-settings`, `python-dotenv`, `google-adk>=1.28`, `litellm`.
- [x] 2.2 Write `.env.example` with `LLM_PROVIDER`, OpenAI/Google keys+models, `BROWSER_HEADLESS`, `FUZZY_MAX_STEPS`.
- [x] 2.3 Write `app/settings.py` using `pydantic-settings`.
- [x] 2.4 Write `app/tools/browser.py` — singleton headed Chromium with lazy launch.
- [x] 2.5 Write `app/tools/actions.py` — async `navigate`, `click`, `fill`, `wait`, `screenshot`, `extract` (stubbed return for POC).
- [x] 2.6 Write `app/agents/model.py` — `get_adk_model()` returning Gemini id string or `LiteLlm("openai/<model>")`.
- [x] 2.7 Write `app/agents/planner.py` — ADK `LlmAgent` with `output_schema=Workflow`, system prompt + 2 few-shots, JSON-mode fallback.
- [x] 2.8 Write `app/agents/fuzzy.py` — ADK `LlmAgent` with Playwright `FunctionTool`s; `before_tool_callback` emits `node_progress`; bounded by `FUZZY_MAX_STEPS`.
- [x] 2.9 Write `app/executor.py` — async graph walker; routes deterministic nodes to `actions.py`, fuzzy nodes to `FuzzyAgent`; emits events via injected callback.
- [x] 2.10 Write `app/main.py` — `GET /api/health`, `GET /api/sample-workflow`, `POST /api/workflow/generate`, `WebSocket /ws/run`.
- [x] 2.11 Write the hardcoded six-node sample workflow used by `/api/sample-workflow`.
- [ ] 2.12 Smoke-check: `python -c "from app.main import app"` imports cleanly.

## 3. Frontend POC (parallel sibling B)

- [x] 3.1 Hand-author `package.json` with Vite/React/TS deps + `@xyflow/react`, `zustand`, `dagre` (no `npm create vite`).
- [x] 3.2 Write `vite.config.ts` with `/api` + `/ws` proxy to `http://localhost:8000`.
- [x] 3.3 Write `tsconfig.json`, `tsconfig.node.json`, `index.html`, `src/main.tsx`.
- [x] 3.4 Write `src/types.ts` (imported in step 1.3) and `src/store.ts` (zustand).
- [x] 3.5 Write `src/components/GlowNode.tsx` with idle/running/success/error CSS + halo keyframes + shimmer subtitle.
- [x] 3.6 Write `src/components/WorkflowCanvas.tsx` with dagre auto-layout and `nodeTypes={glow: GlowNode}`.
- [x] 3.7 Write `src/components/RunLog.tsx` with timestamps and indented progress lines.
- [x] 3.8 Write `src/components/NLInput.tsx` with textarea + "生成工作流" button hitting `/api/workflow/generate`.
- [x] 3.9 Write `src/api.ts` (`getSampleWorkflow`, `generateWorkflow`) and `src/ws.ts` (open `/ws/run`, dispatch events into store).
- [x] 3.10 Write `src/App.tsx` — top bar (NLInput + "运行" + "加载示例"), canvas, RunLog. On mount fetch sample workflow.
- [ ] 3.11 Smoke-check: `npm install && npm run build` (or `tsc --noEmit`) succeeds.

## 4. Integration verification (parent worker)

- [ ] 4.1 Boot backend: `pip install -e .`, `playwright install chromium`, `uvicorn app.main:app --port 8000`.
- [ ] 4.2 `curl http://localhost:8000/api/health` returns `{"ok": true}`.
- [ ] 4.3 Boot frontend: `npm install && npm run dev`. Verify Vite serves on 5173.
- [ ] 4.4 Run a tiny Python WebSocket smoke script: open `/ws/run`, send sample workflow, expect 6× `(node_started, node_completed)` and ≥1 `node_progress` for the fuzzy node, plus a real Chromium window opening.
- [ ] 4.5 If `OPENAI_API_KEY` is set, POST `/api/workflow/generate` with a Chinese description and confirm the returned JSON validates as `Workflow`. Skip otherwise (do not fail).
- [ ] 4.6 Confirm `python -c "from app.agents.fuzzy import FuzzyAgent"` imports cleanly.
- [ ] 4.7 Kill both background processes after verification.

## 5. README and final summary

- [ ] 5.1 Write `auto-agent/README.md` with two-tier "demo mode" / "full mode" instructions, PowerShell commands, two-terminal layout.
- [ ] 5.2 Document deferred work (multi-tab, persistence, anthropic/local models).
