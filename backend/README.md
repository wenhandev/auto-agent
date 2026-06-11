# auto-agent — backend

FastAPI + Google ADK + Playwright. Serves three things:

- `GET  /api/health` — liveness probe.
- `GET  /api/sample-workflow` — hardcoded 6-node demo workflow (no LLM needed).
- `POST /api/workflow/generate` — PlannerAgent: NL description → `Workflow` JSON.
- `WS   /ws/run` — Executor: receives `{type:"start", workflow}`, streams
  `node_started` / `node_progress` / `node_completed` / `node_failed` /
  `run_completed` / `run_failed` events while driving a headed Chromium.

## First-time setup (PowerShell)

```powershell
cd backend
python -m venv .venv          # only if .venv does not already exist
.\.venv\Scripts\Activate.ps1
pip install -e .
playwright install chromium
copy .env.example .env        # optional, only needed for full LLM mode
```

## Run dev server

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --port 8000 --reload
```

## Verify

```powershell
python -c "from app.main import app; print('ok')"
# from repo root, with the server running:
python ..\scripts\ws_smoke.py
python ..\scripts\planner_smoke.py   # optional, skips without LLM key
```

`ws_smoke.py` honors `$env:AUTO_AGENT_PORT` if you need a non-8000 port.

## Config (`.env`)

| Key                | Default              | Notes                                            |
| ------------------ | -------------------- | ------------------------------------------------ |
| `LLM_PROVIDER`     | `openai`             | `openai` or `google` / `gemini`                  |
| `OPENAI_API_KEY`   | —                    | required when provider is `openai`               |
| `OPENAI_MODEL`     | `gpt-4o`             | any LiteLLM-compatible OpenAI model id           |
| `GOOGLE_API_KEY`   | —                    | required when provider is `google` / `gemini`    |
| `GOOGLE_MODEL`     | `gemini-2.0-flash`   | Gemini model id passed directly to ADK           |
| `GOOGLE_BASE_URL`  | —                    | optional: route Google-native Gemini through a relay |
| `BROWSER_HEADLESS` | `false`              | set `true` to hide the Chromium window           |
| `FUZZY_MAX_STEPS`  | `5`                  | hard cap on tool calls per `fuzzy_action` node   |

Without a key the backend still works in demo mode: `PlannerAgent` returns
HTTP 400 with a clear message, and `FuzzyAgent` drops to a 3-step simulated
progress trace in `executor.py` so `/ws/run` always emits a complete event
stream.

## Bosch / internal Gemini relay

The Google ADK normally talks straight to Google AI Studio. To send the
same Google-native Gemini protocol to an internal gateway (e.g. Bosch's
`llmapis.documind.bosch-app.com`) instead, set:

```
LLM_PROVIDER=google
GOOGLE_API_KEY=<gateway key, e.g. sk-...>
GOOGLE_MODEL=gemini-3-flash-preview
GOOGLE_BASE_URL=https://llmapis.documind.bosch-app.com
```

`backend/app/agents/model.py` returns a thin `Gemini` subclass that builds
a `google.genai.Client` with that `base_url` and your gateway key in
`x-goog-api-key`. The genai SDK doesn't validate the key format, so an
`sk-...` gateway key is fine. If the request never reaches the relay
because of the corporate `NO_PROXY` wildcards (httpx rejects `*.foo`-style
patterns at parse time), our subclass already passes `trust_env=False` to
the underlying httpx client to skip env-driven proxying.

If `GOOGLE_BASE_URL` is left unset, ADK falls back to its default —
plain Google AI Studio at `https://generativelanguage.googleapis.com/`.

### Schema strictness fallback

The Gemini API's `response_schema` validator rejects pydantic's
`additionalProperties: true` (which our `Node.params: dict[str, Any]`
emits) with `additionalProperties is not supported in the Gemini API.`
To keep the schema developer-friendly, `PlannerAgent` skips ADK's
`output_schema=Workflow` on the Google branch and instead steers the
model with the strict prompt + few-shot in `planner.py`, then runs the
returned text through `Workflow.model_validate_json` (with one retry on
validation failure). The OpenAI / LiteLlm branch still uses the schema
directly — most OpenAI-compat gateways accept it as-is.
