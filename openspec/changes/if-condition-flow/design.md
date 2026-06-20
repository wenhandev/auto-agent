## Context

The platform ships a DAG scheduler (`app/exec/scheduler.py`) with branch-selecting nodes `condition` (binary) and `switch` (N-way). Edges carry `when: "true"|"false"` or `case: string|null`. Frontend renders multi-port handles for these types (`canvasPorts.ts`, `GlowNode.tsx`).

**Current gaps (verified in code):**

```python
# app/executor.py — condition still uses eval()
result = bool(eval(str(expr), {"__builtins__": {}}, {}))
```

`ConditionPredicate` and `evaluate_predicate()` exist (`schemas.py`, `services/predicate.py`) and power `validation` / `while_loop`, but **`condition` does not call them**. The expression engine (`services/expressions.py`, `{{= ... }}`) is integrated into `variable_interpolation.resolve_params` but condition bypasses it for the final boolean.

Authors add nodes primarily via **chat/planner patches**, not a canvas palette. Demo workflows (`seed_workflow.json`) contain zero branch nodes.

## Goals / Non-Goals

**Goals:**

- Make IF branching **safe**, **predictable**, and **discoverable**.
- One evaluation pipeline shared by `condition`, `switch`, `validation`, and `while_loop` where applicable.
- Preserve scheduler semantics: `Edge.when`, branch pruning, replay dimming — no scheduler changes.
- Backward-compatible for common cases: `predicate` object, whole-field `{{= ... }}`, empty legacy nodes (default-true).

**Non-Goals:**

- Adding a separate `if` node type in `NodeType` (UI alias only).
- Compound boolean trees (AND/OR/NOT) inside one node — authors chain IF nodes.
- Changing `filter` (item-level) or `on_error` branch semantics.
- Rewriting merge/switch topology or fan-out rules.

## Decisions

### Decision 1: Two evaluation modes for `condition` (predicate OR expression)

**Precedence:**

1. If `params.predicate` is present → resolve `left`/`right` via interpolation, then `evaluate_predicate()` → bool.
2. Else if `params.expr` resolves to a bool (whole-field `{{= ... }}` after interpolation) → use that bool directly.
3. Else if `params.expr` is a non-empty string → pass the **interpolated string** to `expressions.evaluate()` as `"{{= " + expr + " }}"` only when it is a bare expression body, OR evaluate as full expression token if already wrapped.
4. Else (empty legacy node) → **default true** (preserve expanded-node-library back-compat).

**Why not eval():** expression-engine exists precisely to forbid this; condition is the last flow-control holdout.

**Alternative rejected:** Jinja `{% if %}` — already rejected in node-context-variables; expressions are sufficient.

### Decision 2: `switch` uses expression engine only

`switch.params.expr` evaluates to a case key via safe expression engine; result stringified for `Edge.case` matching. No `eval()`. Predicate mode deferred (switch is naturally expression-oriented).

### Decision 3: Fail closed on evaluation errors

If predicate or expression evaluation raises `ExpressionError`, `PredicateError`, or `VariableResolutionError`, the condition/switch node **fails** (`node_failed`) — no silent `True` fallback (today eval except → True).

**Migration:** workflows relying on broken expr accidentally taking true branch will change behaviour — acceptable security fix.

### Decision 4: UI label "IF / 条件", internal type stays `condition`

Avoid schema migration and scheduler special cases. Palette inserts `type: "condition"` with label localized. GlowNode shows GitBranch icon (already used for switch — reuse for condition with amber styling).

### Decision 5: Auto-wire true/false edges on insert

When user adds IF node from palette:

- Create node `if_<shortid>` (or user-editable label).
- Create two edges from it: `when: "true"` → placeholder target (or dangling with validation warning), `when: "false"` → placeholder.
- Editor validation MAY warn on dangling edges but MUST NOT block save (same as other nodes).

**Alternative rejected:** single edge + "add branch" wizard — more clicks than n8n IF node.

### Decision 6: Inspector — simple predicate builder + advanced expression tab

Default tab: **Simple** — left token field, op dropdown, right token field (mirrors validation inspector patterns).

Advanced tab: single `expr` textarea with `{{= ... }}` hint and link to expression preview API.

If both `predicate` and `expr` set, **predicate wins** (matches backend).

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| **BREAKING:** legacy bare Python in `expr` stops working | Document in migration; log warning once per run; tests cover common n8n-style expressions via safe engine |
| Authors confuse `filter` vs `condition` | Palette tooltips + planner prompt: "IF = flow branch; Filter = shrink item list" |
| Predicate builder too limited (no AND) | Document chaining; future change for compound predicates |
| Switch case key type coercion | Stringify with explicit rules in spec; test numeric cases |

## Migration Plan

1. Ship backend safe evaluation first (tests green, eval removed).
2. Ship frontend palette + inspector (authors can create IF visually).
3. Update seeded demo with one optional branch (or separate example workflow JSON).
4. Rollback: revert executor dispatch only — UI changes are additive.

## Open Questions

- Should planner emit `predicate` or `expr` by default? **Recommendation:** predicate for simple comparisons, `{{= ... }}` for complex — planner prompt update in tasks.
- Auto-connect IF false branch to `end` node? **Defer** — too opinionated; warn on dangling instead.
