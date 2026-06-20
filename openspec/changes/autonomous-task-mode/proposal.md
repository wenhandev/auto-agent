## depends_on

- `vision-action-mode` — hard dependency. The autonomous loop drives the vision perception layer and tool surface (`vision_navigate`/`vision_act`/`vision_extract`, `click_element`, `extract`, `done`, the `vision_step` event) rather than reinventing browser control.
- `auto-agent-mvp` — executor, `RunEvent` stream, the `nl-workflow-planner` whose graph-generation this mode complements with graph-free execution.
- `auto-agent-platform` — `runtime-llm-config` (the planning/acting LLM), run persistence.
- `run-artifacts-observability` (soft) — per-step screenshots/traces make the autonomous run auditable.

Soft synergy with `expression-engine` / `items-data-model` (the agent can call data nodes as tools) and `human-in-the-loop` (pause for confirmation). No hard dependency on the n8n data-engine track.

## Why

Today auto-agent always needs a **graph**: the planner generates a node/edge workflow, then the executor runs it. Skyvern's headline mode is different — you give it a **URL + a goal** and it autonomously plans, acts, observes, and re-plans until the objective is met, with no pre-authored graph. `vision-action-mode` gives us the per-step vision primitives; this change wraps them in a **closed-loop autonomous agent** with memory, re-planning, guardrails, and a terminal "synthesize a reusable workflow from what I just did" payoff. It is the difference between "run my workflow" and "go accomplish this for me".

## What Changes

- **New run mode `autonomous`** (alongside the existing graph runs): an entry point `POST /api/tasks` accepting `{objective: str, start_url?: str, max_steps?: int, max_seconds?: int, success_criteria?: str, allowed_domains?: [str], data_schema?: JSONSchema, require_confirmation?: bool}`.
- **Agent loop**: `plan → act → observe → reflect → (replan | continue | finish)`. Each cycle: build an observation (perception layer + accumulated memory), ask the LLM for the next action (a vision tool call, a navigation, a data/integration tool call, or `finish`), execute it, record the result, and update a running **scratchpad/memory** and **todo plan**. The loop terminates on `finish(success, result)`, step/time budget exhaustion, a guardrail trip, or an unrecoverable error.
- **Working memory**: a bounded, structured memory (recent observations, extracted facts, the evolving plan, visited URLs) summarised to fit the context window; long runs compact older steps into a summary.
- **Tool surface = superset of vision tools + workflow nodes**: the agent may call the `vision-action-mode` tools AND a curated subset of deterministic nodes as tools (`http_request`, `extract`, data-transform, `integration`) so it can act beyond the browser.
- **Guardrails**: `allowed_domains` allowlist (navigation outside fails the step), step/time budgets, a destructive-action confirmation gate (forms that look like purchases/deletes pause for `human-in-the-loop` when `require_confirmation`), and a loop/no-progress detector (N steps without state change aborts with a diagnostic).
- **Structured result**: when `data_schema` is supplied, `finish` must return data validated against it; otherwise a free-form summary + collected items.
- **Workflow synthesis (the payoff)**: after a successful autonomous run, the agent can emit a **draft reusable workflow** (graph) approximating the trajectory (navigate/vision/extract/data nodes), saved as a normal workflow the user can edit and schedule. This bridges autonomous mode back into the deterministic engine.
- **Events**: reuse `vision_step`; add `task_plan_updated` (the evolving todo plan), `task_reflection` (the agent's self-assessment), `task_finished` (success, result, synthesized_workflow_id?).
- **UI**: a "Task" surface (objective box + start URL) distinct from the graph editor; a live transcript (plan, steps with thumbnails, reflections); a "Save as workflow" action on success.

## Capabilities

### New Capabilities

- `autonomous-agent-loop`: the `autonomous` run mode, the plan-act-observe-reflect cycle, working memory + compaction, the superset tool surface, the structured/free-form result contract, and the `task_*` events.
- `autonomous-guardrails`: domain allowlist, step/time budgets, destructive-action confirmation gate, and no-progress/loop detection with diagnostics.
- `trajectory-to-workflow`: synthesizing a draft reusable graph from a successful autonomous trajectory and saving it as an editable workflow.

### Modified Capabilities

- `vision-action-primitives` (from `vision-action-mode`): the tool surface is invoked by the autonomous loop, not only as standalone nodes; no behaviour change to the primitives themselves.
- `run-history` (from `auto-agent-platform`): new `task_*` events; the run record gains a `mode ∈ {graph, autonomous}` discriminator.
- `nl-workflow-planner` (from `auto-agent-mvp`): graph generation and autonomous mode are presented as two paths; the planner prompt notes when to recommend autonomous mode (open-ended objective) vs a graph (repeatable pipeline).
- `human-in-the-loop`: the confirmation gate consumes its pause/resume mechanism.

## Impact

- **Backend**: `app/agents/autonomous.py` (the loop + memory + reflection), `app/tasks/` run mode + `POST /api/tasks` + a task run record (`mode`, objective, budgets, result), guardrail module, trajectory→graph synthesizer. ~700 LOC + ~400 LOC tests (loop termination, budget/guardrail trips, no-progress detection, schema-validated finish, synthesis shape). Reuses the vision perception/tools and the node executors as callable tools.
- **Frontend**: a Task surface + live transcript + "Save as workflow". ~500 LOC.
- **Runtime**: one LLM call per step (planning/acting) plus reflection calls; cost bounded by `max_steps`/`max_seconds`. Vision steps produce screenshots (artifacts change).
- **Safety**: guardrails are first-class (allowlist, budgets, destructive-action gate); the agent cannot leave allowed domains or exceed budgets; destructive actions require confirmation when configured.
- **Migration**: additive; a new run `mode` column (default `graph`); existing graph runs unaffected.
- **Out of scope**: multi-agent orchestration / sub-agents (single agent loop in v1); learning across tasks / persistent skills (a future `agent-skill-memory`); CAPTCHA solving (`captcha-antibot-proxy`); fully unattended runs without any budget (budgets are mandatory); replacing the graph engine (autonomous mode complements it).
