## Why

We want a single-developer prototype that proves a tight loop between "describe a browser task in natural language" and "watch a browser do it" — with the same JSON serving as both the flowchart in the UI and the executable plan on the backend. Existing automation tools either expose only the script (no visual graph) or only the canvas (no execution). The MVP unifies both so the user sees the active node glow in real time while a real Chromium window navigates pages.

## What Changes

- New greenfield repo layout: `backend/` (FastAPI + Python) and `frontend/` (Vite + React + TS).
- A shared `Workflow` JSON schema (nodes + edges + `start_id`) used by planner, UI, and executor as the single contract.
- A custom async graph walker in `app/executor.py` (not ADK's runner) so we own per-node WebSocket event timing.
- Use **ADK's built-in model abstraction** for all LLM calls:
  - **Gemini** via the native string id (`"gemini-2.0-flash"`), which ADK accepts directly.
  - **OpenAI** via ADK's `LiteLlm(model="openai/gpt-4o")` wrapper.
- A small `app/agents/model.py` helper picks the right ADK model object from `.env`. No custom adapter layer of our own.
- `PlannerAgent` is an ADK `LlmAgent` with `output_schema=Workflow` (structured JSON output). One-shot call. We fall back to JSON-mode + `Workflow.model_validate_json` with one retry if `output_schema` proves unreliable through `LiteLlm`.
- `FuzzyAgent` is an ADK `LlmAgent` with Playwright actions registered as `FunctionTool`s and a `before_tool_callback` that emits `node_progress` events to the WebSocket.
- A custom React Flow `GlowNode` with four visual states (`idle | running | success | error`) and a shimmer subtitle for fuzzy progress.
- A demo path (`/api/sample-workflow`) that requires **no** API key, so the prototype is runnable today.

## Capabilities

### New Capabilities
- `workflow-schema`: The shared `Workflow / Node / Edge` JSON contract emitted by the planner, rendered by the canvas, and walked by the executor.
- `nl-workflow-planner`: Natural-language → `Workflow` JSON via an ADK `LlmAgent` with `output_schema=Workflow`.
- `workflow-canvas`: React Flow canvas with a custom `GlowNode` and `dagre` auto-layout.
- `hybrid-executor`: Async graph walker that runs deterministic nodes via Playwright actions and routes `fuzzy_action` nodes to the FuzzyAgent.
- `live-event-stream`: WebSocket `/ws/run` emitting `node_started / node_completed / node_failed / node_progress` events as the executor walks the graph.
- `fuzzy-action-agent`: ADK `LlmAgent` with Playwright `FunctionTool`s, vision input, a bounded multi-step loop, and a `before_tool_callback` for sub-step progress.
- `adk-model-helper`: A small `get_adk_model()` helper that returns either the Gemini model string or a `LiteLlm("openai/<model>")` instance based on `.env`.

### Modified Capabilities
(none — greenfield)

## Impact

- Creates a new repository under `auto-agent/` with two top-level apps.
- New backend dependencies: `fastapi`, `uvicorn[standard]`, `playwright`, `pydantic>=2`, `pydantic-settings`, `python-dotenv`, `google-adk` (>= 1.28), `litellm`.
- New frontend dependencies: `@xyflow/react`, `zustand`, `dagre`.
- Adds an external runtime requirement: a Playwright-managed headed Chromium installation (`playwright install chromium`).
- LLM keys are optional for the demo flow but required for `/api/workflow/generate` and the real fuzzy loop.
