## depends_on

- `items-data-model` — these nodes consume `input_items` and emit `items`; this is their entire reason to exist.
- `expression-engine` — field values and predicates use `{{= ... }}` expressions (e.g. `set` assigns `{{= item.json.price * 1.2 }}`).
- `node-context-variables` — token resolution for non-expression fields.
- `expanded-node-library` — establishes the `app/nodes/<type>.py` module layout and the per-type params/output discriminator pattern these nodes follow.

Soft sibling of `dag-executor-merge` (Merge handles fan-in; these handle per-item reshaping). No browser dependency — all nodes are pure data.

## Why

After `items-data-model`, records flow as item arrays, but auto-agent has no nodes to *reshape* them. n8n's most-used nodes are not integrations — they are the data utilities: **Set/Edit Fields**, **Filter**, **Sort**, **Limit**, **Aggregate**, **Split Out**, **Remove Duplicates**, **Rename Keys**, and **Date/Time**. Without them, every transform degenerates into an `http_request` to a helper service or a (refused) Code node. These nodes are small, pure, deterministic, and items-aware — the natural payoff of the items model.

## What Changes

- **New node types** on the `NodeType` literal, each a pure items→items transform:
  - `set` (a.k.a. Edit Fields): set/keep/remove fields on each item's `json` via a list of assignments `{name, value}` where `value` may be a literal or a `{{= ... }}` expression; modes `manual` (assign listed fields) with options `keep_only_set` and `include_binary`.
  - `filter`: keep items where a `{{= ... }}` predicate is truthy; output the surviving items.
  - `sort`: order items by one or more `{field, order}` keys (expression or path), stable.
  - `limit`: keep the first/last N items.
  - `aggregate`: collapse all items into one — `concat` a field into a list, or `sum`/`avg`/`min`/`max`/`count` a numeric field, or `group_by` a key producing one item per group.
  - `split_out`: explode an array field of one item into N items (n8n "Split Out"), carrying the rest of the json.
  - `remove_duplicates`: drop items duplicate on a key set (first-wins), with a `compare ∈ {all_fields, selected_fields}` option.
  - `rename_keys`: rename json keys per a `{from, to}` list.
  - `datetime`: produce/transform a datetime — `now`, `parse`, `format`, `add`/`subtract` a duration — into a chosen field.
- **Per-type params/output models** registered through the existing discriminator; one module per type under `app/nodes/<type>.py`.
- **All nodes are items-aware**: they read `input_items`, operate over the array (or per item), and emit `items`. `output` (the back-compat alias) is the first emitted item.
- **Editor / planner prompts**: catalogue entries (params + behaviour + one example each), emphasising expressions in `set`/`filter`.
- **UI**: NodeInspector type-specific forms (assignment rows for `set`, predicate field for `filter`, key list for `sort`/`remove_duplicates`, etc.); canvas icons per type; RunLog shows item-count deltas (e.g. `filter: 10 → 3`).

## Capabilities

### New Capabilities

- `field-mutation-nodes`: `set`/Edit Fields, `rename_keys`, `datetime` — per-item json mutation with expression-valued fields.
- `item-list-nodes`: `filter`, `sort`, `limit`, `aggregate`, `split_out`, `remove_duplicates` — array-level reshaping over items.

### Modified Capabilities

- `workflow-schema` (from `auto-agent-mvp`): `NodeType` grows by nine literals.
- `hybrid-executor` (from `auto-agent-mvp`): dispatch table grows; all new nodes consume `input_items` and emit multi-item `NodeResult`s.
- `non-browser-action-nodes` / `composite-flow-nodes` (from `expanded-node-library`): the `app/nodes/` catalogue grows with the new modules.
- `run-history` (from `auto-agent-platform`): `node_completed.items_count` makes filter/aggregate deltas visible (no new event types needed).
- `chat-authoring` / `nl-workflow-planner`: prompts grow by the catalogue.

## Impact

- **Backend**: 9 node modules under `app/nodes/` (~30–90 LOC each), executor dispatch additions, all reusing `expression-engine` for expression fields and the items envelope. ~600 LOC + ~400 LOC tests (per node + edge cases: empty input, non-numeric aggregate, missing key).
- **Frontend**: 9 per-type forms, 9 icons, item-count delta in RunLog. ~500 LOC.
- **Runtime**: pure in-memory transforms bounded by `max_items_per_node`; no I/O, no LLM (except expression evaluation which is itself bounded).
- **Migration**: additive node types; no DB migration.
- **Out of scope**: pivot/unpivot and crosstab (future `data-reshape-advanced`); SQL-style multi-table joins (Merge `merge_by_key` covers the common case); the Code node (refused); spreadsheet/Excel parsing (a future `office-doc-parsing` change); streaming aggregation over unbounded inputs (items are materialised + capped).
