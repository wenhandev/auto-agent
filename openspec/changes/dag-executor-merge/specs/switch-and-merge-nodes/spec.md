## Description

`switch` routes to one of N outgoing edges by a case key; `merge` is a fan-in node with four modes. `Edge` gains an optional `case` used by `switch` (parallel to `when` used by `condition`). `condition` remains a 2-case special form internally routed through the same selection logic.

## User stories

- **As a workflow author**, I want to branch into more than two paths based on a value (status == "paid" / "pending" / "failed"), not just true/false.
- **As a workflow author**, I want to merge two branches' items back into one stream (append) or join them on a key.
- **As a workflow author**, I want a merge to still produce output when one of its branches was skipped.

## ADDED Requirements

### Requirement: Switch Node Case Routing

A `switch` node SHALL evaluate `params.expr` (an expression via `expression-engine`, or a typed predicate) to a case key, then select the outgoing edge whose `case` equals the key. If no edge matches, it SHALL select the edge with `case == null` (default). If no default exists, the node SHALL fail with `"switch: no case matched '<key>' and no default edge"`.

#### Scenario: Matching case selected

- **WHEN** `switch` evaluates to `"paid"` and there are edges `case="paid"`, `case="pending"`, `case=null`
- **THEN** only the `case="paid"` edge SHALL be selected; the others SHALL be pruned.

#### Scenario: Default fallback

- **WHEN** `switch` evaluates to `"unknown"` and edges are `case="paid"`, `case=null`
- **THEN** the `case=null` (default) edge SHALL be selected.

#### Scenario: No match and no default fails

- **WHEN** `switch` evaluates to `"x"` and no edge has `case="x"` or `case=null`
- **THEN** the node SHALL fail with an error containing `"no case matched 'x' and no default edge"`.

### Requirement: Merge Node Modes

A `merge` node SHALL support `mode ∈ {"append", "merge_by_key", "wait_all", "pass_through"}`. `append` SHALL concatenate all non-pruned parents' items in parent-edge order. `merge_by_key` SHALL join items on `params.key`, later parents overriding on collision. `wait_all` SHALL emit a single item whose json maps each parent id to that parent's `output`. `pass_through` SHALL emit the first-arrived parent's items.

#### Scenario: Append concatenates items

- **WHEN** parent `b` emits items `[{x:1}]` and parent `c` emits `[{x:2},{x:3}]` into an `append` merge
- **THEN** the merge SHALL emit items whose json values are `[{x:1},{x:2},{x:3}]`.

#### Scenario: Merge by key joins records

- **WHEN** `b` emits `[{id:1, a:"A"}]`, `c` emits `[{id:1, b:"B"}]`, mode is `merge_by_key`, `key="id"`
- **THEN** the merge SHALL emit one item `{id:1, a:"A", b:"B"}`.

#### Scenario: wait_all keys by parent id

- **WHEN** parents `b` and `c` complete with outputs `Ob` and `Oc` into a `wait_all` merge
- **THEN** the merge SHALL emit a single item whose json is `{"b": Ob, "c": Oc}`.

### Requirement: Merge Tolerates Skipped Branches

When some incoming edges to a `merge` were pruned (their branch was skipped), the merge SHALL proceed using only the arrived (non-pruned) parents and SHALL NOT wait for the pruned ones.

#### Scenario: Merge after a skipped branch

- **WHEN** an `append` merge has parents `b` (ran) and `c` (skipped because its branch was pruned)
- **THEN** the merge SHALL emit `b`'s items only, without deadlocking on `c`.

### Requirement: Edge Case Field And Condition Compatibility

`Edge` SHALL accept an optional `case: str | null` used by `switch`. The existing `condition` node and `Edge.when` SHALL remain valid and SHALL be routed through the same internal selection logic as a 2-case form.

#### Scenario: Condition still works

- **WHEN** a `condition` node has `when="true"` and `when="false"` outgoing edges and evaluates true
- **THEN** the `when="true"` edge SHALL be selected exactly as before this change.

## Out of Scope

- Loop nodes (`foreach`/`while`).
- Merge strategies beyond the four listed (e.g. SQL-style outer joins) — future change.
