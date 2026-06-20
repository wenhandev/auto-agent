## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Add `ExpressionError` to a new module `backend/app/services/expressions.py`; export.
- [x] 1.2 `[shared-contract]` Add settings `expr_max_len=2048`, `expr_max_nodes=500`, `expr_max_iter=10000`, `expr_timeout_ms=250` to `backend/app/settings.py`.
- [x] 1.3 `[shared-contract]` Add Pydantic `ExpressionPreviewRequest`/`ExpressionPreviewResponse` to `backend/app/schemas_api.py`; TS mirrors in `frontend/src/types-platform.ts`; `apiClient.expressions.preview` stub in `frontend/src/api-platform.ts`.
- [ ] 1.4 `[shared-contract]` Smoke-check imports + `tsc --noEmit`.

## 2. Evaluator core (Sibling A — `[backend-security]`)

- [x] 2.1 Implement `expressions.evaluate(expr: str, namespace: dict) -> Any`: length check; `ast.parse(mode="eval")`; whitelist visitor over `ALLOWED_NODES`; AST node-count cap.
- [x] 2.2 Implement the recursive interpreter over allowed nodes (BinOp/BoolOp/UnaryOp/Compare/IfExp/Subscript/Slice/List/Dict/Set/Tuple/comprehensions/Call/Attribute/Name/Constant). No `eval`/`compile`/`exec`.
- [x] 2.3 Implement the attribute resolver: per-type method allowlist; reject any name starting/ending with `_`; reject attributes off the allowlist.
- [x] 2.4 Implement the call resolver: `SAFE_FUNCTIONS` table + per-type method allowlist; reject all else. Gate `str.format` to reject attribute/index field specs.
- [x] 2.5 Implement iteration cap (wrap comprehensions/`range`/`map`/`filter`) and the cooperative wall-clock deadline checked per interpreter step.
- [x] 2.6 Implement namespace builder from a `NodeResult` context + current `item`/`items`/`params`/`now`; optional read-only n8n aliases (`$json`,`$node`,`$now`).
- [x] 2.7 Error contract: `ExpressionError` message with truncated expr + sanitised cause + available names.

## 3. Adversarial test corpus (Sibling A continued — `[backend-security]`)

- [x] 3.1 `backend/tests/test_expressions_safety.py` MUST reject: `__import__('os')`, `().__class__`, `[].__class__.__mro__`, `''.__class__.__bases__`, `(1).__class__`, generator `gi_frame`, `getattr/setattr/globals/locals/open/eval/exec`, `lambda`, walrus, `{0.__class__}`.format abuse, deeply nested billion-laughs comprehension (iteration cap), 3 KB source (length cap), an infinite-ish comprehension (timeout).
- [x] 3.2 `backend/tests/test_expressions_eval.py` MUST accept and compute: arithmetic, comparison, boolean, conditional, subscript/slice, list/dict comprehension with filter, allowed builtins, string-method allowlist, date helpers, `json_parse`/`json_stringify`.
- [x] 3.3 Whole-expression type preservation vs interpolated stringify tests.

## 4. Interpolation routing (Sibling A continued — `[backend-runtime]`)

- [x] 4.1 In `backend/app/services/variable_interpolation.py`, detect a token whose first non-space char is `=`; strip it; call `expressions.evaluate(remainder, namespace)`. Pure-path tokens unchanged.
- [x] 4.2 Build the namespace from the executor's per-run `NodeResult` context + current item scope.
- [x] 4.3 Tests: `{{= ... }}` routes to evaluator; `{{nodes...}}` routes to path resolver; mixed text stringifies.

## 5. Preview endpoint + prompts (Sibling A continued)

- [x] 5.1 `POST /api/expressions/preview` in `backend/app/routers/` — reuse the evaluator + latest-successful-run predecessor outputs; return `{ok,type,value_preview,error}`; `{ok:false,error:"no run data"}` when none.
- [x] 5.2 Append the expression catalogue (form + namespace + allowed functions + 2-3 examples) to `editor.py` and `planner.py` system prompts.
- [ ] 5.3 Tests: preview with/without run data; substring test for prompt catalogue.

## 6. Frontend (Sibling B — `[frontend]`)

- [ ] 6.1 Render `{{= ... }}` fields with a monospace expression chip distinct from path chips; an "fx" affordance toggles a field into expression mode.
- [ ] 6.2 "fx" popover calls `apiClient.expressions.preview` and shows `value_preview`/`error` against the latest run.
- [ ] 6.3 Smoke-check: `npm run build`; author an expression field, see live preview.

## 7. Verification (parent worker)

- [ ] 7.1 `[verification]` End-to-end: a workflow with a field `"{{= nodes.<id>.output.<num> * 2 }}"`; confirm the downstream node receives the doubled value.
- [ ] 7.2 `[verification]` Safety: author `"{{= ().__class__ }}"`; confirm `node_failed` with an `ExpressionError` and no object leakage.
- [ ] 7.3 `[verification]` Limits: author an over-cap comprehension; confirm failure names the iteration cap.
- [ ] 7.4 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Backend security/runtime `[backend-security]` + `[backend-runtime]`
**Mission.** Evaluator, allowlists, limits, adversarial tests, interpolation routing, preview endpoint, prompts (§2–§5).
**Owns.** `backend/app/services/expressions.py`, the safety/eval tests, `variable_interpolation.py` routing, the preview router, `editor.py`/`planner.py` prompt edits.
**Must NOT touch.** `frontend/`, action signatures.
**Independent verification.** `pytest backend/tests/test_expressions_safety.py backend/tests/test_expressions_eval.py` green; the safety corpus is the gate.

### Sibling B — Frontend `[frontend]`
**Mission.** Expression chip + fx preview (§6).
**Owns.** Inspector expression field + preview popover, TS mirrors, the `preview` api method body.
**Must NOT touch.** Backend evaluator.

**Shared contract deps (§1).** `ExpressionError`, settings, preview request/response types.
