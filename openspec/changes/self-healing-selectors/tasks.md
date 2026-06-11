## 1. Shared contract (parent worker)

- [ ] 1.1 `[shared-contract]` Extend `backend/app/schemas.py`:
  - add optional `auto_heal: bool = True` field to the params model for `click` and `fill` (via a small per-type params model registered through the discriminator the platform change already uses).
- [ ] 1.2 `[shared-contract]` Extend `backend/app/db/models.py::LlmConfig`:
  - add column `self_healing_enabled: bool = Field(default=True)`;
  - add column `self_healing_vision_threshold: float = Field(default=0.6, ge=0.0, le=1.0)` — the DOM-to-vision escalation boundary per design Decision 5.
- [ ] 1.3 `[shared-contract]` Extend `backend/app/schemas_api.py`:
  - event-type literal grows to include `"node_self_healed"`, `"node_self_heal_failed"`;
  - add `NodeSelfHealedPayload(BaseModel)` (`original_selector`, `new_selector`, `confidence`, `mode: Literal["dom","vision"]`, `cost_hint`);
  - add `NodeSelfHealFailedPayload(BaseModel)` (`original_selector`, `reason: Literal["low_confidence","no_candidate","post_heal_action_failed","agent_error"]`, `mode: Literal["dom","vision"]`, `agent_confidence`, `original_error`, `post_heal_error`, `cost_hint`);
  - `LlmConfigOut` / `LlmConfigUpsert` include `self_healing_enabled` AND `self_healing_vision_threshold`.
- [ ] 1.4 `[shared-contract]` Mirror TS types in `frontend/src/types-platform.ts`:
  - `LlmConfig` includes `self_healing_enabled` AND `self_healing_vision_threshold`;
  - event-type union grows;
  - `NodeSelfHealedPayload`, `NodeSelfHealFailedPayload` (including the `mode` discriminator).
- [ ] 1.5 `[shared-contract]` Author `backend/app/db/migrations.py::self_healing_default_on_first_run()` — idempotent helper that ensures `self_healing_enabled = True` AND `self_healing_vision_threshold = 0.6` on the existing `LlmConfig` row (if any) and writes marker `backend/.self_healing_default_set`. Wire into `lifespan` after `init_db()` and the other migrations.
- [ ] 1.6 `[shared-contract]` Append `.self_healing_default_set` to `.gitignore`.
- [ ] 1.7 `[shared-contract]` Smoke-check: `python -c "from app.db.models import LlmConfig; lc = LlmConfig(provider='x', model='y'); assert lc.self_healing_enabled is True; print('ok')"` and `cd frontend && npx tsc --noEmit` pass.

## 2. Backend self-healing (Sibling A — `[backend]`)

- [ ] 2.1 Author `backend/app/agents/selector_finder.py`:
  - `SelectorFinderAgent` ADK `LlmAgent`;
  - constructed lazily via `get_adk_model_cached()`;
  - one tool: `propose_selector(selector_description: str, confidence: float) -> dict` (the agent calls this; the tool just records the args);
  - system prompt per design Decision 4 explaining the task with one few-shot.
- [ ] 2.2 Author `backend/app/services/self_healing.py`:
  - `_is_enabled(node, session) -> bool` checks the active `LlmConfig.self_healing_enabled` AND `node.params.auto_heal`;
  - `_vision_threshold(session) -> float` reads the active `LlmConfig.self_healing_vision_threshold` (default `0.6`);
  - `wrap_action(action_fn, node, page, *, emit, session)` per design Decision 1;
  - `attempt_heal(page, node, original_error) -> HealResult` implements the two-stage flow per design Decision 5:
    1. **DOM stage**: capture only `page.accessibility.snapshot()`; invoke `SelectorFinderAgent(ax_tree=...)` inside `asyncio.wait_for(..., 15.0)`; record `(selector, confidence, mode="dom")`; accumulate `cost_hint`;
    2. **Decide**: if `confidence >= _vision_threshold(session)`, skip vision and use the DOM result;
    3. **Vision stage (only when DOM confidence is below the threshold)**: capture `page.screenshot(mask=[<password fields>])`; re-invoke `SelectorFinderAgent(ax_tree=..., screenshot=...)`; record `(selector, confidence, mode="vision")`; aggregate `cost_hint` so it reflects the SUM of both calls;
    4. apply the 0.5 confidence threshold per design Decision 3 (using the final-stage `(selector, confidence)` pair);
    5. return `HealResult(healed, new_selector, confidence, mode, cost_hint, failure_reason)`.
- [ ] 2.3 Modify `backend/app/executor.py::_dispatch` (or whatever the existing helper is named that picks the action coroutine for a node) — for nodes of type `click` and `fill`, wrap the action with `self_healing.wrap_action(...)`. Pass an `emit` closure that records the event via the existing `services.runs.record_event` path. Other node types are dispatched untouched.
- [ ] 2.4 Implement the action-failure detection: catch `playwright.async_api.TimeoutError` specifically (not a generic `Exception`) so other action failures bubble through without triggering a heal.
- [ ] 2.5 Implement the "vision-not-supported short-circuit" — if `attempt_heal` raises a recognisable provider error indicating the active model has no vision capability, set a process-wide flag `_VISION_SUPPORTED = False` for the rest of the run; subsequent `wrap_action` calls within the same run see the flag and skip the heal entirely (emitting `node_self_heal_failed(reason="agent_error")` only on the first failure).
- [ ] 2.6 Update `backend/app/routers/llm_config.py` — `POST /api/llm-config` and `PUT /api/llm-config/{id}` accept `self_healing_enabled` AND `self_healing_vision_threshold`. `GET` responses include both. Activation does NOT invalidate the heal flag (it's per-config, not per-cache).
- [ ] 2.6a Update `backend/app/agents/editor.py` system prompt — append a one-shot example mapping the canonical user message `"将节点 <id> 的 selector 改为 \"<new>\""` to an `update_node` patch whose `patch.params = {"selector": "<new>"}`. This makes the "采用新选择器" chat prefill flow reliable across editor LLM models.
- [ ] 2.7 Add unit tests `backend/tests/test_self_healing_service.py`:
  - `_is_enabled` returns true / false combinations of the global and per-node toggles;
  - `wrap_action` invokes the inner action and returns on success without contacting the heal service;
  - `wrap_action` on `TimeoutError` invokes `attempt_heal`; on a high-confidence candidate, retries the action with the new selector; on a low-confidence candidate, re-raises the original;
  - `attempt_heal` masks password inputs in the vision stage's screenshot (assert via the `mask` parameter passed to `page.screenshot`);
  - **DOM-first happy path**: stub the agent so the DOM call returns `(".x", 0.75)`; with `self_healing_vision_threshold = 0.6`, confirm `mode="dom"`, `cost_hint.vision_calls == 0`, AND that `page.screenshot` was NEVER called;
  - **Vision-fallback path**: stub the agent so the DOM call returns `(".x", 0.45)` and the vision call returns `(".y", 0.91)`; with threshold `0.6`, confirm `mode="vision"`, `cost_hint.vision_calls == 1`, `new_selector == ".y"`, AND that `page.screenshot` WAS called exactly once;
  - **Combined cost aggregation**: in the vision-fallback case, confirm `cost_hint.input_tokens` is the SUM of both agent calls' input tokens (when token usage is available);
  - 15 s timeout wraps each agent call independently.
- [ ] 2.8 Add integration test `backend/tests/test_self_healing_integration.py`:
  - stub the `SelectorFinderAgent` to return a fixed `(selector=".new", confidence=0.9)`;
  - run a 3-node workflow where a `click` node's selector deliberately fails on the first try (use a Playwright route to make `#old` never match) and where `.new` matches;
  - assert one `node_self_healed` event, the action completes, the run terminates `completed`.
- [ ] 2.9 Smoke-check: `pytest backend/tests/test_self_healing_service.py backend/tests/test_self_healing_integration.py -v` passes.

## 3. Frontend (Sibling B — `[frontend]`)

- [ ] 3.1 Update the RunLog renderer (semantic role — the live event stream component) to recognise `node_self_healed` and `node_self_heal_failed` events. Healed rows render with a wand icon, the `mode` chip (`DOM` or `Vision`), and the "采用新选择器" button. Failed-heal rows render with a faded wand icon, the `mode` chip, and a tooltip showing the reason.
- [ ] 3.2 Author `frontend/src/healing/AdoptHealedSelectorButton.tsx`:
  - on click, opens the chat panel (via the existing public API of whichever component owns the panel — semantic role only);
  - pre-fills the composer text per design Decision 8 with the LOCKED template `"将节点 <node_id> 的 selector 改为 \"<new>\""` (no old-selector text; the editor agent looks up the current value);
  - sets focus to the send button (does NOT auto-send).
- [ ] 3.3 Update the Settings page to render two heal-related controls:
  - global toggle `自动自愈选择器` reading / writing `LlmConfig.self_healing_enabled`;
  - threshold slider `视觉自愈阈值` (range `0.0`–`1.0`, step `0.05`, default `0.6`) reading / writing `LlmConfig.self_healing_vision_threshold` with help text explaining: below this confidence, the DOM-only first attempt escalates to a more expensive vision call. Set to `0.0` for DOM-only, `1.01` for always-vision.
- [ ] 3.4 Update the NodeInspector (semantic role — the existing inspector that renders per-type params forms) to render the per-node `auto_heal` switch on `click` and `fill` nodes. Default on; off renders a small "已禁用自愈" muted label next to the selector input.
- [ ] 3.5 Update the canvas to render a small wand badge on healed nodes during run replay (consume `node_self_healed` events and overlay the badge). Disappears when the replay is reset.
- [ ] 3.6 Update the RunReplay player to handle the two new event types (render them in the log; the badge overlay handled by §3.5).
- [ ] 3.7 Smoke-check: `pnpm build` clean; `tsc --noEmit` clean.

## 4. Verification (parent worker)

- [ ] 4.1 `[verification]` Author a tiny test page with two buttons (`#old` and `.new`); deliberately route `#old` to nothing for the duration of the test. Author a 3-node workflow that clicks `#old`. Confirm a `node_self_healed` event AND the run terminates `completed`. The healed selector (`.new`) is logged.
- [ ] 4.2 `[verification]` Disable `LlmConfig.self_healing_enabled` via the Settings page; re-run; confirm NO heal event AND the run fails with the original `TimeoutError`.
- [ ] 4.3 `[verification]` Re-enable globally; set `node.params.auto_heal = false` on the click node via the inspector; re-run; confirm NO heal event AND the run fails.
- [ ] 4.4 `[verification]` Re-enable both; run; in the run log click "采用新选择器"; confirm the chat composer is pre-filled with the exact locked template `"将节点 <id> 的 selector 改为 \".new\""` AND the editor's resulting patch (after the operator clicks send) changes the node's `selector` to `.new`. Confirm NO bypass endpoint exists (sanity check: `grep -r "applyHeal" frontend/src/ backend/app/` returns no matches).
- [ ] 4.5 `[verification]` Low confidence: stub the agent to return `confidence=0.3` (via a test-only env var); re-run; confirm `node_self_heal_failed(reason="low_confidence")` AND the run fails with the original error AND NO post-heal action retry.
- [ ] 4.6 `[verification]` Vision-not-supported: temporarily activate an `LlmConfig` row pointing at a text-only model (or simulate); confirm `node_self_heal_failed(reason="agent_error")` fires once AND subsequent `click` failures in the same run skip the heal entirely (no further `node_self_heal_failed` events on the same reason).
- [ ] 4.7 `[verification]` Abort during heal: kick off a run that triggers a heal; immediately click 停止 while the LLM is presumably running; confirm `run_aborted` AND the heal task was cancelled (no `node_self_healed` event).
- [ ] 4.8 `[verification]` Cost hint visible: confirm `node_self_healed.cost_hint` is populated when the active LLM returns token counts AND that the run log row shows the tooltip with the token numbers AND the `mode` chip (`DOM` or `Vision`).
- [ ] 4.8a `[verification]` DOM-first behaviour: stub the agent (via a test-only env var) so the DOM call returns a high-confidence candidate; trigger a heal; confirm the resulting `node_self_healed.mode == "dom"` AND `cost_hint.vision_calls == 0`.
- [ ] 4.8b `[verification]` Vision-fallback behaviour: lower `self_healing_vision_threshold` to `0.95` via the Settings slider so a typical DOM hit escalates; trigger a heal against a fixture that the DOM stage solves at `~0.78`; confirm the resulting `node_self_healed.mode == "vision"` AND `cost_hint.vision_calls == 1` AND that the chosen selector is the vision-stage candidate.
- [ ] 4.9 `[verification]` Backwards compat: a workflow generated before this change runs unchanged when the global toggle is off AND when the toggle is on with no `click` / `fill` failures.
- [ ] 4.10 `[verification]` Kill all dev processes.

## 5. README

- [ ] 5.1 Update `auto-agent/README.md` — new "自愈选择器 / Self-healing selectors" section: how it works, cost guidance, global toggle, per-node opt-out, the "采用新选择器" flow.

---

## Parallel Implementation Plan

Two sibling workers after the parent lands §1.

### Sibling A — Backend `[backend]`

**Mission.** Selector finder agent, heal service, action wrapper, executor dispatch wiring, LlmConfig field. All of §2.

**Owns.** `backend/app/agents/selector_finder.py` (new), `backend/app/services/self_healing.py` (new), `backend/app/executor.py` (dispatch wiring for `click` / `fill` only), `backend/app/routers/llm_config.py` (extend the existing CRUD for the new field), `backend/app/db/migrations.py` (the new helper — though parent-owned in §1.5, sibling can extend), all of `backend/tests/test_self_healing_*.py`.

**Must NOT touch.** Anything under `frontend/`, `backend/app/tools/actions.py` (action signatures unchanged), other agents (`fuzzy.py`, `extractor.py`, `editor.py`, `planner.py`), the `Run` / `RunEvent` schemas beyond the event-type literal in §1.

**Shared contract deps (§1).** `node.params.auto_heal`, `LlmConfig.self_healing_enabled`, event-type literal extension, `NodeSelfHealed{,Failed}Payload`.

**Independent verification.** `pytest backend/tests/test_self_healing_*.py` passes; the integration test against the stubbed agent walks through a heal end-to-end.

**Estimated tasks.** ~9 (2.1–2.9).

### Sibling B — Frontend `[frontend]`

**Mission.** RunLog event variants, "采用新选择器" chat prefill, Settings toggle, NodeInspector switch, canvas badge. All of §3.

**Owns.** `frontend/src/healing/AdoptHealedSelectorButton.tsx` (new), RunLog renderer extension, Settings page toggle, NodeInspector switch for `click` / `fill`, canvas badge overlay on replay, RunReplay player extension.

**Must NOT touch.** Backend files, `frontend/src/store.ts` (consumes via existing public API only), `frontend/src/chat/` internals (uses the chat panel's public mount / composer-prefill API only).

**Shared contract deps (§1).** Extended `LlmConfig` TS type, event-type literal extension, `NodeSelfHealed{,Failed}Payload`.

**Independent verification.** Against a running Sibling-A backend, set up the test-page workflow that deliberately fails its first selector, run it, see the heal event in the log, click "采用新选择器", confirm the chat composer is pre-filled. Toggle the global setting off, confirm the heal disappears.

**Estimated tasks.** ~7 (3.1–3.7).

### Rationale

Self-healing is a small, contained change: one service + one agent + one action wrapper on the backend, one event-row variant + one button + one settings toggle on the frontend. The two siblings share only the event-payload shapes and the `LlmConfig` field — all parent-owned in §1. The integration test on the backend can run independently of the frontend; the frontend can develop against a stubbed event stream by injecting a fake `node_self_healed` event into the run log.
