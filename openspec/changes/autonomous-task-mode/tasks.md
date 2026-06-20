## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add a run `mode` column (`graph`|`autonomous`, default `graph`) via migration; add a task run record (objective, budgets, success_criteria, allowed_domains, data_schema, allowed_tools, result).
- [x] 1.2 `[shared-contract]` Define `TaskSpec` / `TaskResult` Pydantic models; `POST /api/tasks` contract; `task_plan_updated` / `task_reflection` / `task_finished` event types.
- [x] 1.3 `[shared-contract]` TS mirrors for `TaskSpec`/`TaskResult`/task events; `apiClient.tasks.create`/`.get` stubs.
- [x] 1.4 `[shared-contract]` Smoke-check imports + migration + `tsc --noEmit`.

## 2. Agent loop + memory (Sibling A — `[backend-agent]`)

- [x] 2.1 `app/agents/autonomous.py`: the plan-act-observe-reflect loop driving `vision-action-mode` perception/tools; one tool call per step; `finish` tool; reflection every K steps.
- [x] 2.2 `Memory`: objective, plan (todo subgoals), recent observations, extracted items, visited URLs; compaction that preserves data items verbatim.
- [x] 2.3 Superset tool surface: vision tools + nodes-as-tools (`http_request`/`extract`/data-transform/`integration`) generated from node params; restrict to `allowed_tools`.
- [x] 2.4 Result contract: schema-validated `finish` (one corrective retry) or `{success, summary, items}`.
- [x] 2.5 Emit `task_plan_updated`/`task_reflection`/`task_finished` + reuse `vision_step`.
- [x] 2.6 Tests `backend/tests/test_autonomous_loop.py`: finish terminates; step/time budget terminates; tool restriction enforced; schema-valid finish; invalid finish retries then fails; data items survive compaction.

## 3. Guardrails (Sibling B — `[backend-safety]`)

- [x] 3.1 Domain allowlist check on navigation/`http_request`; blocked-message failure.
- [x] 3.2 Mandatory budget enforcement (steps + wall clock) outside the LLM.
- [x] 3.3 Destructive-action classifier + `human-in-the-loop` confirmation gate; `integration` writes always gate under `require_confirmation`.
- [x] 3.4 No-progress detector (URL + element-map hash + no-new-data over M steps) with diagnostic abort.
- [x] 3.5 Tests `backend/tests/test_autonomous_guardrails.py`: off-allowlist blocked; time budget; purchase pause; integration-write pause; repeated no-op abort.

## 4. Trajectory synthesis (Sibling A continued — `[backend-agent]`)

- [x] 4.1 Synthesizer: trajectory → draft graph (navigate/vision/extract/data nodes), prefer vision nodes where selectors were unstable; save as `status="draft"`; set `task_finished.synthesized_workflow_id`.
- [x] 4.2 Tests `backend/tests/test_trajectory_synthesis.py`: draft created with referenced id; unstable step yields a vision node; draft marked for review.

## 5. Planner routing + prompts (parent worker)

- [ ] 5.1 Planner prompt: route open-ended objectives to autonomous mode, repeatable pipelines to graph generation; document the distinction.
- [ ] 5.2 Substring regression test for the routing guidance.

## 6. Frontend (Sibling C — `[frontend]`)

- [x] 6.1 A "Task" surface: objective box + start URL + budgets/allowed-domains/schema options, distinct from the graph editor.
- [ ] 6.2 Live transcript: plan (todo), steps with thumbnails + thought + action, reflections; abort control.
- [ ] 6.3 "Save as workflow" action on success (opens the synthesized draft in the editor).
- [ ] 6.4 Smoke-check: `npm run build`; run a small autonomous task against a local page and watch the transcript.

## 7. Verification (parent worker)

- [ ] 7.1 `[verification]` Autonomous task on a controlled local site: agent navigates, extracts, and finishes within budget; structured result matches a supplied schema.
- [ ] 7.2 `[verification]` Guardrails: off-allowlist navigation blocked; a destructive action pauses under `require_confirmation`; a forced no-op loop aborts with a diagnostic.
- [ ] 7.3 `[verification]` Synthesis: after success, a draft workflow exists and runs (after review) on the same site.
- [ ] 7.4 `[verification]` Existing graph runs are unaffected (mode defaults to graph).
- [ ] 7.5 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Agent loop + synthesis `[backend-agent]`
**Owns.** `app/agents/autonomous.py`, memory/compaction, tool surface, result contract, trajectory synthesizer, the loop/synthesis tests.
**Must NOT touch.** Guardrail module internals (consume its interface), frontend, the vision primitives themselves.

### Sibling B — Guardrails `[backend-safety]`
**Owns.** Domain allowlist, budget enforcement, destructive-action gate + `human-in-the-loop` wiring, no-progress detector, guardrail tests.
**Must NOT touch.** The loop's planning internals (expose `check_*` hooks the loop calls), frontend.

### Sibling C — Frontend `[frontend]`
**Owns.** Task surface, live transcript, save-as-workflow, TS mirrors.
**Must NOT touch.** Backend.

**Shared contract deps (§1).** Run `mode`, `TaskSpec`/`TaskResult`, `POST /api/tasks`, task events. Interface seam A↔B: guardrail `check_navigation/check_action/check_progress` hooks + the budget clock.
