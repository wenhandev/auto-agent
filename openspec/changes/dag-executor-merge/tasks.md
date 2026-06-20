## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add `switch`, `merge` to the `NodeType` literal in `backend/app/schemas.py`; add optional `case: str | None` to `Edge`.
- [x] 1.2 `[shared-contract]` Add event-type literals `branch_pruned`, `node_skipped`, `merge_waiting` to the run-event contract.
- [x] 1.3 `[shared-contract]` TS mirrors in `frontend/src/types-platform.ts` (`NodeType`, `Edge.case`, new event types).
- [ ] 1.4 `[shared-contract]` Smoke-check imports + `tsc --noEmit`.

## 2. Scheduler (Sibling A — `[backend-executor]`)

- [x] 2.1 Author `backend/app/exec/scheduler.py`: indegree over incoming edges; ready-queue; deterministic ordering (topo rank, then node_id); per-node run via the existing `_run_node` (interpolation, retry/on-error, context, events preserved).
- [x] 2.2 Implement edge selection: plain node selects all `next` edges (fan-out); `condition` 2-case; `switch` case routing; on-error routing integrated with `node-error-handling`.
- [x] 2.3 Implement pruning + the all-incoming-pruned skip rule + skip propagation; emit `branch_pruned` / `node_skipped`.
- [x] 2.4 Implement cycle detection (back-edge outside a loop construct) failing at run start with `"cycle detected"`.
- [x] 2.5 Replace `run_workflow`'s walk with the scheduler; keep `emit`, context (`NodeResult`), and the single-tab sequential ready-set seam `run_ready_set`.
- [x] 2.6 Tests `backend/tests/test_scheduler.py`: linear parity; diamond runs both branches then merges once; pruning + skip propagation; one-live-one-pruned parent runs; cycle rejected; deterministic ordering.

## 3. Switch + Merge nodes (Sibling A continued — `[backend-executor]`)

- [x] 3.1 Implement `switch` dispatch: evaluate `params.expr` (expression-engine when present, else typed predicate) to a case key; select matching `case` edge / `case=null` default / fail when neither.
- [x] 3.2 Implement `merge` dispatch with modes `append` / `merge_by_key` (`params.key`) / `wait_all` / `pass_through`; the scheduler holds `merge` until non-pruned parents complete; emit `merge_waiting`.
- [x] 3.3 Implement merge-tolerates-skipped-branch: proceed with arrived parents, no deadlock.
- [x] 3.4 Tests `backend/tests/test_switch_merge.py`: switch match/default/no-match-fail; append/merge_by_key/wait_all/pass_through; merge after a skipped branch.

## 4. Prompts (Sibling A continued)

- [x] 4.1 Document `switch`/`merge` (params, when to prefer over `condition`) in `editor.py` and `planner.py` system prompts with one example each.
- [x] 4.2 Substring regression tests for the catalogue additions.

## 5. Frontend (Sibling B — `[frontend]`)

- [x] 5.1 Canvas: render `switch` (multi-output ports per case) and `merge` (multi-input) nodes with distinct icons.
- [x] 5.2 Replay: render pruned edges and skipped nodes dimmed; show `merge_waiting` state on the merge node.
- [ ] 5.3 NodeInspector forms: `switch` cases (+ default) and `merge` mode/key.
- [ ] 5.4 Smoke-check: `npm run build`; build and replay a diamond workflow.

## 6. Verification (parent worker)

- [ ] 6.1 `[verification]` Regression: run the seeded `示例工作流`, the Apple workflows, and a `condition`-branch fixture; assert identical observable behaviour (event sequence modulo new types).
- [ ] 6.2 `[verification]` Diamond: build `a -> {b,c} -> d(merge append)`; confirm `d` runs once with concatenated items.
- [ ] 6.3 `[verification]` Switch: build a 3-case switch; confirm only the matching branch runs and others are skipped.
- [ ] 6.4 `[verification]` Merge after skipped branch: confirm no deadlock and correct output.
- [ ] 6.5 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Backend executor `[backend-executor]`
**Mission.** Scheduler, switch/merge dispatch, prompts (§2–§4).
**Owns.** `backend/app/exec/scheduler.py` (new), `backend/app/executor.py` (traversal swap), switch/merge handlers, `editor.py`/`planner.py` prompt edits, the scheduler/switch/merge tests.
**Must NOT touch.** `frontend/`, action signatures, `items-data-model`'s `NodeResult` (consume only).
**Independent verification.** `pytest backend/tests/test_scheduler.py backend/tests/test_switch_merge.py` green; the linear/condition parity fixtures are the gate.

### Sibling B — Frontend `[frontend]`
**Mission.** Multi-port switch/merge rendering, dimmed replay, inspector forms (§5).
**Owns.** Canvas node renderers, replay dim states, inspector forms, TS mirrors.
**Must NOT touch.** Backend scheduler.

**Shared contract deps (§1).** `NodeType` additions, `Edge.case`, new event types.
