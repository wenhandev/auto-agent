## depends_on

- `expression-engine` — `{{= ... }}` safe evaluator; condition/switch MUST use this instead of Python `eval`.
- `dag-executor-merge` — DAG scheduler, branch pruning, `Edge.when` / `Edge.case` routing (already shipped).
- `expanded-node-library` — `ConditionPredicate` schema and typed predicate evaluator (`app/services/predicate.py`); condition node SHOULD reuse it.
- `node-context-variables` — variable interpolation for `left`/`right` and whole-field expressions.

This change **productizes** conditional flow that already exists at the engine level but is unsafe, hard to discover, and inconsistently implemented.

## Why

Workflow authors need **IF / ELSE branching** on extracted data, HTTP status, file contents, and parameters — the same capability n8n, Power Automate, and UiPath expose as a first-class block. auto-agent already has `condition`, `switch`, and `merge` node types and a DAG scheduler, but:

1. **`condition` still evaluates `params.expr` via Python `eval()`** after interpolation — bypassing the safe expression engine and creating a security/behaviour split.
2. **`ConditionPredicate` exists in schema but is not wired into `condition`** — validation/while_loop use typed predicates; condition does not.
3. **Authors cannot easily add an IF node from the canvas** — no node palette entry, no auto-created true/false edges, demo workflows are linear-only.
4. **UI labels say "condition" not "IF"** — discoverability is poor for non-technical users.

Without fixing this, every real automation either stays linear or authors hack branching with fuzzy_action / manual JSON edits.

## What Changes

- **Remove `eval()` from `condition` and `switch`** — evaluate via safe expression engine (`{{= ... }}` whole-field) and/or typed `ConditionPredicate`; fail the node with actionable errors on evaluation failure (no silent default-true).
- **Unify evaluation precedence for `condition`**: if `predicate` is set → typed evaluator; else if `expr` is a whole `{{= ... }}` field → expression engine; else if legacy bare `expr` → deprecate with migration warning in logs/docs (treat as expression string through safe evaluator, not `eval`).
- **Switch expression path** — `params.expr` SHALL use the same safe evaluation pipeline as condition (expression engine namespace: `nodes`, `item`, `items`, `params`, `now`).
- **Authoring UI — "IF 条件" node** — canvas node library entry for `condition` (display label IF / 条件); inserting auto-creates two outgoing edges (`when="true"`, `when="false"`) with localized port labels.
- **Inspector UX** — structured predicate builder (left / op / right) with variable picker OR advanced `{{= ... }}` expression mode; expression preview reuses `POST /api/expressions/preview`.
- **Switch authoring** — optional palette entry + inspector for `expr` and per-edge `case` labels (builds on existing switch type).
- **Demo / docs** — add one sample branch to seeded workflow or a dedicated fixture workflow demonstrating IF on extracted JSON.
- **Planner / chat prompts** — document when to use IF (`condition`) vs `switch` vs `filter`.

## Capabilities

### New Capabilities

- `condition-safe-evaluation`: normative rules for how `condition` and `switch` evaluate expressions and predicates; removal of `eval`; error contract; output shape `{predicate?, expr?, result}` / `{switch_case}`.
- `if-condition-authoring-ui`: canvas palette, auto-wiring true/false edges, inspector forms, i18n labels (IF / 条件), replay dimming unchanged (owned by dag-executor-merge).

### Modified Capabilities

- (none in archived `openspec/specs/` — requirements live in sibling change folders; this change adds standalone spec files that supersede the incomplete `condition` sections in `expanded-node-library` and `dag-executor-merge` at implementation time.)

## Impact

- **Backend**: `app/executor.py` condition/switch dispatch (~40 LOC refactor); reuse `app/services/predicate.py`, `app/services/expressions.py`; optional `ConditionParams` pydantic model in `schemas.py`. ~150 LOC tests (predicate, expression, legacy compat, switch cases).
- **Frontend**: node palette component (~120 LOC), condition inspector predicate builder (~200 LOC), i18n keys, GlowNode icon for condition (GitBranch). ~250 LOC total.
- **Security**: closes the remaining `eval()` hole in flow-control nodes.
- **Migration**: existing workflows with bare `expr` strings continue to work if mappable to safe expressions; truly arbitrary Python in `expr` will start failing (intentional **BREAKING** for unsafe expressions only).
- **Out of scope**: new node type alias `if` in schema (UI label only); compound AND/OR predicates (chain IF nodes); loop nodes; changing merge/switch topology rules.
