## Description

The executor schedules nodes by indegree over active edges: a node runs when all its incoming edges are resolved and at least one was selected; it is skipped when all incoming edges are pruned. Branch-selecting nodes prune non-selected edges, and skips propagate. Linear and condition-only workflows execute identically to before. Cycles outside loop constructs fail at run start.

## User stories

- **As a workflow author**, I want a diamond (split then merge) to execute each branch once and then continue, instead of failing with "cycle detected".
- **As a workflow author**, I want a non-selected branch to be skipped, and any node reachable only through skipped edges to be skipped too.
- **As an operator**, I want replay to show which edges were pruned and which nodes were skipped.
- **As an existing user**, I want my linear and condition workflows to behave exactly as before.

## ADDED Requirements

### Requirement: Indegree Ready-Queue Scheduling

The executor SHALL run a node only after every incoming edge to that node is resolved (its source ran and marked the edge selected or pruned). A node with no incoming edges (the start node) SHALL be initially ready. When multiple nodes are ready, the executor SHALL run them in a deterministic order (ascending topological rank, then ascending `node_id`).

#### Scenario: Linear chain unchanged

- **WHEN** a workflow is a linear chain `n1 -> n2 -> n3`
- **THEN** the nodes SHALL execute in order `n1, n2, n3` and the emitted event sequence SHALL match the pre-change behaviour (aside from additive event types).

#### Scenario: Diamond executes both branches then merges

- **WHEN** the graph is `a -> b`, `a -> c`, `b -> d`, `c -> d` (d is a merge)
- **THEN** `a` SHALL run first, then `b` and `c` (deterministic order), then `d` exactly once after both `b` and `c` complete.

### Requirement: Branch Pruning And All-Incoming-Pruned Skip

A branch-selecting node (`condition`, `switch`, or on-error routing) SHALL mark its non-selected outgoing edges pruned. A node SHALL be skipped (emitting `node_skipped`) only when ALL of its incoming edges are pruned; if at least one incoming edge is selected, the node SHALL run. A skipped node SHALL prune all of its outgoing edges (skip propagation).

#### Scenario: Non-selected branch is skipped

- **WHEN** a `condition` selects its `when="true"` edge to `b` and prunes the `when="false"` edge to `c`, and `c` has no other incoming edge
- **THEN** `c` SHALL be skipped with a `node_skipped` event AND its downstream-only nodes SHALL also be skipped.

#### Scenario: Node with one live and one pruned parent still runs

- **WHEN** node `d` has incoming edges from `b` (selected) and `c` (pruned via a skipped branch)
- **THEN** `d` SHALL run (at least one incoming edge selected), not be skipped.

### Requirement: Cycle Detection Outside Loop Constructs

A graph containing a back-edge that is not part of a recognised loop construct SHALL fail at run start with a `run_failed` event whose error contains `"cycle detected"`.

#### Scenario: Illegal cycle rejected

- **WHEN** the graph contains `n1 -> n2 -> n1` with no loop node
- **THEN** the run SHALL fail immediately with an error containing `"cycle detected"`.

### Requirement: Scheduler Events

The executor SHALL emit `branch_pruned` (with `node_id`, `edge_id`), `node_skipped` (with `node_id`), and `merge_waiting` (with `node_id`, `arrived`, `expected`) events. Replay SHALL handle these without error.

#### Scenario: Pruned and skipped events emitted

- **WHEN** a condition prunes an edge causing a downstream node to be skipped
- **THEN** a `branch_pruned` event SHALL be emitted for the pruned edge AND a `node_skipped` event for the skipped node.

### Requirement: Single-Tab Sequential Execution Preserved

Even when multiple nodes are ready, the executor SHALL run them sequentially in v1 so browser actions never overlap on the shared Chromium tab.

#### Scenario: Ready set runs sequentially

- **WHEN** `b` and `c` are both ready after `a`
- **THEN** they SHALL execute one at a time in the deterministic order, never concurrently.

## Out of Scope

- True parallel execution / browser pool (`concurrent-runs-browser-pool`).
- Loop constructs (`foreach`/`while`).
- Distributed scheduling.
