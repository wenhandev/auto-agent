## depends_on

- `auto-agent-mvp` — the workflow schema (`Node`, `Edge`, `start_id`), the single-cursor executor walker, and the binary `condition` node + `Edge.when` branch semantics this change generalises.
- `items-data-model` — Merge concatenates item arrays; the executor already threads `NodeResult.items`.
- `node-error-handling` (soft) — `Edge.kind="on_error"` and the on-error policy must keep working under the new scheduler; not a hard dependency but co-designed.

This change is the control-flow foundation for `data-transform-nodes` and any non-linear workflow. No dependency on browser-intelligence changes.

## Why

The executor ([backend/app/executor.py](backend/app/executor.py)) is a single-cursor walker with a `visited` set that forbids re-entering a node. That makes three n8n staples impossible: (1) a node with two parents (fan-in / **Merge**), (2) multi-way branching beyond true/false (**Switch**), and (3) any diamond-shaped graph. Today `condition` only picks between a `when="true"` and `when="false"` edge. To reach n8n-level flow control we replace the walker with an indegree-driven DAG scheduler and add `switch` and `merge` node types.

## What Changes

- **Executor rewrite to a DAG scheduler**: replace the single `current_id` + `visited` walk with a ready-queue scheduler driven by per-node indegree over the *active* edges. A node becomes runnable when all of its active incoming edges have been resolved (its parents ran and selected the edge toward it, or pruned it). Linear workflows behave exactly as before.
- **Branch pruning**: when a `condition`/`switch` node selects one outgoing edge, the non-selected edges are marked pruned; their downstream subgraphs are skipped UNLESS a surviving path also reaches them (a node is skipped only when ALL its incoming active edges are pruned). This yields correct diamonds.
- **New node type `switch`**: evaluates an expression (via `expression-engine` when present, else a typed predicate) to a case key; routes to the outgoing edge whose `case` matches, else the `default` edge. `Edge` gains an optional `case: str | null` used by `switch` (parallel to `when` used by `condition`).
- **New node type `merge`**: a fan-in node with `mode ∈ {"append", "merge_by_key", "wait_all", "pass_through"}`. `append` concatenates all parents' items; `merge_by_key` joins items on a key field; `wait_all` waits for every parent then emits a combined item; `pass_through` forwards the first parent to arrive. The scheduler holds a `merge` node until its required parents complete.
- **Parallel branches**: independent ready nodes MAY run; because browser actions share one Chromium tab, browser nodes are serialized through a lock while non-browser nodes (http/parse/set) MAY overlap. v1 executes the ready set sequentially in a deterministic order (topological + node-id tiebreak) to preserve today's single-tab semantics; the scheduler is structured so true concurrency is a later `concurrent-runs-browser-pool` change.
- **Cycle handling**: the DAG must be acyclic except through explicit loop nodes (`foreach`/`while`, owned elsewhere). A back-edge that is not a loop body SHALL fail validation with a clear cycle error (same spirit as today's `cycle detected`).
- **New events**: `branch_pruned` (node_id, edge_id), `merge_waiting` (node_id, arrived, expected). `node_skipped` for nodes whose all-incoming edges were pruned.
- **UI**: canvas renders `switch` (multi-port) and `merge` (multi-input) nodes; pruned edges/nodes shown dimmed during replay; NodeInspector forms for `switch` cases and `merge` mode.

## Capabilities

### New Capabilities

- `dag-scheduler`: the indegree/ready-queue executor, branch pruning, all-incoming-pruned skip rule, deterministic ready-set ordering, cycle detection, and the `branch_pruned` / `node_skipped` / `merge_waiting` events.
- `switch-and-merge-nodes`: the `switch` node (case routing via expression/predicate, `Edge.case`) and the `merge` node (`append` / `merge_by_key` / `wait_all` / `pass_through`).

### Modified Capabilities

- `hybrid-executor` (from `auto-agent-mvp`): the traversal algorithm is replaced; the per-node run/emit/context steps are preserved. `condition` + `Edge.when` semantics are subsumed as a 2-case special form.
- `workflow-schema` (from `auto-agent-mvp`): `NodeType` gains `switch`, `merge`; `Edge` gains optional `case`.
- `run-history` (from `auto-agent-platform`): new event types `branch_pruned`, `node_skipped`, `merge_waiting`; replay handles them.
- `node-error-handling` (from its change): the on-error branch picker is reimplemented against the scheduler; `kind="on_error"` edges integrate with pruning.
- `chat-authoring` / `nl-workflow-planner`: prompts document `switch`/`merge` and when to use them over `condition`.

## Impact

- **Backend**: `app/executor.py` traversal replaced (~250 LOC) with a scheduler module `app/exec/scheduler.py`; `switch`/`merge` dispatch (~120 LOC); schema additions; new events. ~250 LOC tests incl. diamond, multi-parent merge, pruning, cycle detection, on-error-under-scheduler regression.
- **Frontend**: multi-port switch/merge rendering, dimmed pruned elements in replay, inspector forms. ~300 LOC.
- **Runtime**: scheduler overhead is O(V+E); ready-set executed sequentially in v1 (single tab preserved). No DB migration (schema fields live in `workflow_json`; events are additive).
- **Migration**: existing linear and condition-only workflows run identically (a linear chain has indegree 1 throughout; `condition` maps to a 2-case switch internally). The seeded sample and Apple workflows are unaffected.
- **Out of scope**: true parallel browser execution / browser pool (`concurrent-runs-browser-pool`); loop nodes `foreach`/`while` (owned by `expanded-node-library` / `vision-and-utility-blocks`, revisited for items); distributed scheduling.
