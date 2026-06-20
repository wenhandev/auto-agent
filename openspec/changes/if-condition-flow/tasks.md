## 1. Safe evaluation (backend)

- [x] 1.1 `[backend]` Extract shared helper `evaluate_condition(params, namespace) -> bool` in `app/services/flow_conditions.py` (or extend `predicate.py`) implementing precedence from `condition-safe-evaluation` spec.
- [x] 1.2 `[backend]` Refactor `executor.py` `condition` dispatch: remove `eval()`; call helper; output `{result, predicate?, expr?}`.
- [x] 1.3 `[backend]` Refactor `executor.py` `switch` dispatch: remove `eval()`; use `expressions.evaluate`; stringify case key.
- [x] 1.4 `[backend]` Fail closed: map `ExpressionError`, `PredicateError`, `VariableResolutionError` to `node_failed` (remove silent `except: True`).
- [x] 1.5 `[backend]` Add `ConditionParams` pydantic model to `schemas.py` if not already wired on `Node.params` validation path.
- [x] 1.6 `[backend]` Unit tests: `tests/test_condition_flow.py` — predicate, whole-field expr, legacy empty default-true, malicious expr rejected, switch case/default/no-match, scheduler pruning integration (reuse fixtures from `test_switch_merge.py`).

## 2. Authoring UI (frontend)

- [x] 2.1 `[frontend]` Add node palette / toolbar with **IF / 条件** entry → inserts `condition` node.
- [x] 2.2 `[frontend]` On IF insert: auto-create `when=true` and `when=false` outgoing edges (dangling targets OK).
- [x] 2.3 `[frontend]` `ConditionParamsEditor` component: Simple (predicate builder) + Advanced (`expr` + preview hook) tabs in NodeInspector.
- [x] 2.4 `[frontend]` GlowNode: branch icon for `condition` (distinct from switch if needed).
- [x] 2.5 `[frontend]` i18n keys in `en.json`, `zh-CN.json`, `zh-TW.json` for palette, edges, inspector.
- [x] 2.6 `[frontend]` (Optional) Switch palette + case editor on edges.
- [x] 2.7 `[frontend]` Smoke: `npm run build` clean.

## 3. Authoring prompts & demo

- [x] 3.1 `[backend]` Update `planner.py` / chat editor prompts: IF vs switch vs filter guidance with one example each.
- [x] 3.2 `[demo]` Add branch example — either extend `demo/seed_workflow.json` with optional IF path OR add `demo/branch_workflow.json` + seed helper.

## 4. Verification

- [x] 4.1 `[verification]` Regression: `pytest tests/test_scheduler.py tests/test_switch_merge.py tests/test_expressions_eval.py` green.
- [ ] 4.2 `[verification]` Manual: add IF from palette → set predicate status>=400 → run workflow with HTTP node → observe true/false branch in replay (dimmed pruned path).
- [x] 4.3 `[verification]` Security: confirm `grep -r "eval(" backend/app/executor.py` has no condition/switch eval paths.

---

## Parallel plan

Single worker recommended — backend evaluation + frontend inspector share `ConditionPredicate` shape.

**Suggested order:** §1 → §2 → §3 → §4.
