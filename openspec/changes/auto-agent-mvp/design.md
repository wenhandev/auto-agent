## Context

`auto-agent` is a local single-user POC for natural-language-driven browser automation. The architecture is a tight loop where the *same JSON* serves as (a) the LLM's structured output, (b) the flowchart in the UI, and (c) the executable plan on the backend. The active node "glows" in the UI because the executor broadcasts per-node WebSocket events keyed by the same `node.id` that React Flow already knows about. Target environment: Windows 11, Python 3.11+, Node 22.

Two LLM call shapes show up: one-shot structured generation (planner) and a multi-step vision+tools loop (fuzzy actions). Both are handled by ADK's existing model abstraction; we add no abstraction of our own.

## Goals / Non-Goals

**Goals:**
- Demonstrable end-to-end loop today (open Chromium, watch nodes glow).
- Single canonical `Workflow` schema shared across planner, UI, and executor.
- Multi-provider LLM support (OpenAI + Google Gemini) reachable from a single `.env` flag.
- Keep ADK as the agent-orchestration framework for the fuzzy loop and structured planner output.
- Demo path (`/api/sample-workflow`) that requires zero API keys.

**Non-Goals:**
- Streaming model output to the UI.
- Multi-user isolation, auth, persistence beyond in-memory state.
- Record-and-replay of user interactions.
- Custom LLM adapters, custom `BaseLlm` subclasses, anthropic/local-model support in the POC.

## Decisions

### 1. One shared `Workflow` JSON schema, owned by the backend
- Defined as `pydantic` models in `backend/app/schemas.py`.
- Mirror frontend types live in `frontend/src/types.ts`, written by hand to match.
- The planner is told to emit this exact shape; the executor and the canvas consume the same JSON without translation.
- **Why**: the moment we have two schemas, the "active node glows" trick stops being free.

### 2. Custom async graph walker, not ADK's runner, for the executor
- File: `app/executor.py`.
- ADK's runner does not give us per-node WebSocket hooks at the right granularity, and we already know the graph statically.
- The walker awaits one action per node and emits events through an injected `on_event` async callback. The callback writes JSON frames to the WebSocket.
- **Alternatives considered**: ADK `GraphAgent` (no — too much coupling for a static known graph), homegrown sync walker (no — must `await` Playwright).

### 3. Plan A — use ADK's built-in models exclusively
- **No custom adapter code.** `app/llm/` does not exist.
- For Gemini, ADK accepts a model-id string directly: `LlmAgent(model="gemini-2.0-flash", ...)`.
- For OpenAI, we use ADK's bundled `LiteLlm` wrapper: `LlmAgent(model=LiteLlm(model="openai/gpt-4o"), ...)`.
- A small helper `app/agents/model.py` reads `.env` and returns the right model object. That is the entire abstraction.
- **Why**: ADK already provides a `BaseLlm` interface and ships `LiteLlm` for the long tail of providers. Adding our own adapter layer would duplicate this and force us to maintain an ADK glue subclass (`AdapterBackedLlm`) on top of ADK's own abstraction. Two layers do the work of one — kill our layer.
- **Trade-off accepted**: OpenAI calls go through LiteLLM rather than the native `openai` SDK, so we lose `client.beta.chat.completions.parse`'s pydantic-native structured output. ADK's `output_schema` + LiteLLM's JSON-mode is enough for our `Workflow` planner; we add one JSON-mode + `model_validate_json` retry as a safety net.

### 4. Planner = ADK `LlmAgent` with `output_schema=Workflow`
- One-shot, no tools, no loop.
- The system prompt enumerates the allowed `NodeType`s, the `params` keys each accepts, the rules ("use the user's own vocabulary in `label`", "one user-perceivable step per node"), and two few-shot examples (a precise deterministic flow and a mixed deterministic + `fuzzy_action` flow).
- Verification at implementation time: `python -c "from google.adk.agents import LlmAgent; import inspect; print(inspect.signature(LlmAgent.__init__))"` to confirm the structured-output kwarg name. If the installed version doesn't accept `output_schema`, use whatever name it does accept (e.g. `response_schema`, `output_pydantic`), or fall back to JSON-mode + manual validation.

### 5. FuzzyAgent = ADK `LlmAgent` with Playwright `FunctionTool`s
- Constructed once per `fuzzy_action` execution; the Playwright `Page` from the singleton browser is closed over by the tool functions.
- Tools registered: `click_text`, `click_selector`, `fill_field`, `scroll`, `screenshot`, `done`.
- A `before_tool_callback` (or the closest equivalent in the installed ADK version) emits a `node_progress` event with a short message like `"调用 click_text('登录')"` BEFORE the tool body runs.
- Loop bound: `settings.fuzzy_max_steps` (default 5). If ADK exposes a max-iteration setting on `LlmAgent`, use it; otherwise wrap the runner with a counter.

### 6. Headed Chromium singleton, one process-wide instance
- `app/tools/browser.py` lazily launches `chromium.launch(headless=settings.browser_headless)` on first use.
- One `Page` is shared across the executor's deterministic actions AND the FuzzyAgent's tools — both see the same DOM state.
- Concurrency: one run at a time. Not a concern for the POC.

### 7. WebSocket protocol
- Client → server: one `{"type":"start", "workflow": <Workflow>}` frame.
- Server → client: `{event, node_id, ts, ...payload}` frames; events are `run_started`, `node_started`, `node_progress` (fuzzy only), `node_completed`, `node_failed`, `run_completed`, `run_failed`.
- Per-action errors become `node_failed` frames; the WS handler does not raise.

### 8. Frontend stack: Vite + React + TS + @xyflow/react + zustand + dagre
- `GlowNode` keyed by `data.status`. CSS `@keyframes pulseHalo` for running halo, a shimmer gradient for the fuzzy subtitle.
- `dagre` recomputes positions on workflow replacement.
- Zustand store: `workflow`, `runStatus`, `Map<nodeId, {status, message}>`.

### 9. POC demo path stays alive without API keys
- `/api/sample-workflow` returns a hardcoded six-node `Workflow` exercising `navigate / wait / fuzzy_action / extract / navigate / wait`. The frontend fetches it on mount.
- The "运行" button always runs the current store workflow, so the demo flow works whether or not the user has generated one via `/api/workflow/generate`.

## Risks / Trade-offs

- **ADK `LlmAgent` API drift** → Mitigation: at implementation time, inspect the installed `LlmAgent.__init__` signature and ADK's tool-callback API; write against the installed shape, not docs.
- **Structured output through `LiteLlm` may be flaky for some OpenAI models** → Mitigation: `Workflow.model_validate_json` fallback with one retry, and a clear error to the client if both fail.
- **Headed Chromium pop-up annoys the user during dev** → Mitigation: `BROWSER_HEADLESS=true` in `.env` for non-demo dev.
- **Fuzzy loop bound** → ADK's runner may not expose a hard max-iteration; if so, we wrap with our own counter so the loop can't run away.
- **No persistence** → Workflows live in memory and in the browser only. First-class persistence is deferred.
- **Single-tab Chromium** → Two workflows can't run concurrently. Acceptable for local prototype.
- **`before_tool_callback` is the assumed hook name; the installed ADK version may use a different name.** → Mitigation: introspect `LlmAgent` for any `*_callback` kwargs at implementation time and pick the correct one.

## Migration Plan

N/A — greenfield.

## Open Questions

- Confirm at install time which ADK kwarg names actually exist (`output_schema` vs `output_pydantic`, `before_tool_callback` vs `tool_callback`, etc.). Resolve by reading installed package source.
- Confirm whether `pip show google-adk` already pins `litellm` (it typically does); if so, we don't need to declare `litellm` in `pyproject.toml` separately.
