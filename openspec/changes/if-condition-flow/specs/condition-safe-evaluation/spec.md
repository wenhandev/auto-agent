## Description

Normative evaluation rules for `condition` (IF/ELSE) and `switch` flow-control nodes. Removes Python `eval()` from branch selection. Unifies with `expression-engine` and `ConditionPredicate` / `evaluate_predicate()`.

## User stories

- **As a workflow author**, I want `IF status >= 400` to branch safely using upstream HTTP output without writing Python.
- **As a workflow author**, I want `{{= nodes.extract.output.count > 0 }}` in a condition node to work like any other expression field.
- **As a security owner**, I want no flow-control node to call Python `eval()` or `exec()`.
- **As an existing user**, I want legacy condition nodes with no params to keep taking the true branch.

## ADDED Requirements

### Requirement: Condition Evaluation Precedence

A `condition` node SHALL evaluate its branch decision using the following precedence:

1. If `params.predicate` is a valid `ConditionPredicate` object, the executor SHALL resolve `left` and optional `right` through the standard variable interpolation pass, then evaluate via `evaluate_predicate()` and map the bool to `Edge.when` (`"true"` / `"false"`).
2. Else if `params.expr` is present and, after interpolation, the resolved value is already a `bool`, the executor SHALL use that bool directly.
3. Else if `params.expr` is present and non-empty after interpolation, the executor SHALL evaluate it through the safe expression engine (`expressions.evaluate`) with the standard namespace (`nodes`, `item`, `items`, `params`, `now`) and coerce the result to `bool`.
4. Else (no predicate and empty/missing expr), the executor SHALL treat the result as `true` (legacy default-true behaviour).

The node output SHALL include at minimum `{"result": bool}` and SHOULD include serialised `predicate` and/or `expr` when present.

#### Scenario: Typed predicate numeric comparison

- **WHEN** `predicate = {left: "{{nodes.http.output.status}}", op: ">=", right: 400}` and HTTP status is `500`
- **THEN** the condition SHALL evaluate `true` AND select the outgoing edge with `when="true"`.

#### Scenario: Whole-field expression evaluates to bool

- **WHEN** `expr` is exactly `{{= nodes.n1.output.count > 0 }}` and `nodes.n1.output.count` is `3`
- **THEN** the condition SHALL evaluate `true`.

#### Scenario: Legacy empty condition defaults true

- **WHEN** a condition node has `{}` params (no predicate, no expr)
- **THEN** the condition SHALL evaluate `true` AND follow the `when="true"` edge if present.

#### Scenario: Predicate wins over expr when both set

- **WHEN** both `predicate` and `expr` are set and predicate evaluates `false` while expr would evaluate `true`
- **THEN** the condition SHALL evaluate `false` (predicate precedence).

### Requirement: Condition And Switch Must Not Use Python eval

The executor SHALL NOT call Python `eval()` or `exec()` when evaluating `condition` or `switch` nodes.

#### Scenario: Malicious expr rejected safely

- **WHEN** `expr` contains `{{= __import__('os').system('id') }}`
- **THEN** evaluation SHALL raise `ExpressionError` AND the node SHALL fail with `node_failed` (not silently true).

### Requirement: Evaluation Errors Fail The Node

When predicate evaluation raises `PredicateError`, expression evaluation raises `ExpressionError`, or interpolation raises `VariableResolutionError` during condition/switch evaluation, the executor SHALL emit `node_failed` with an actionable message. It SHALL NOT fall back to `true`.

#### Scenario: Missing variable fails condition

- **WHEN** `predicate.left` is `{{nodes.missing.output.x}}` and the path cannot be resolved
- **THEN** the condition SHALL fail before branch selection.

#### Scenario: Expression error fails condition

- **WHEN** `expr` is `{{= 1 / 0 }}` or another expression error
- **THEN** the condition SHALL fail with a message referencing the expression.

### Requirement: Switch Safe Expression Routing

A `switch` node SHALL evaluate `params.expr` through the safe expression engine after interpolation, stringify the result (empty string for `None`), and select the outgoing edge whose `case` equals that key. If no edge matches, it SHALL select the edge with `case == null` (default). If no default exists, the node SHALL fail with an error containing `no case matched`.

#### Scenario: Switch matches case

- **WHEN** `expr` evaluates to `"paid"` and edges have `case="paid"`, `case="pending"`, `case=null`
- **THEN** only the `case="paid"` edge SHALL be selected.

#### Scenario: Switch uses default

- **WHEN** `expr` evaluates to `"unknown"` and edges are `case="paid"`, `case=null`
- **THEN** the `case=null` edge SHALL be selected.

### Requirement: Scheduler Integration Unchanged

Branch selection results from condition/switch evaluation SHALL feed the existing DAG scheduler edge-selection logic (`when` / `case`, branch pruning, `node_skipped`). This change SHALL NOT alter merge, on_error routing, or fan-out rules.

#### Scenario: False branch pruned

- **WHEN** a condition evaluates `false` with outgoing edges `when="true"` → `b` and `when="false"` → `c`, and `c` has no other incoming edges
- **THEN** edge to `c` SHALL be pruned AND `c` SHALL be skipped per dag-scheduler rules.

## Out of Scope

- Compound predicates (AND/OR/NOT) inside one condition node.
- New `NodeType` value `if` in persisted workflow JSON.
- Changing `filter` node semantics (item-level, not flow-level).
