## Description

Per-item nodes that mutate each item's `json`: `set` (Edit Fields), `rename_keys`, and `datetime`. Each maps over `input_items`, evaluating expression-valued fields with `item` bound to the current item, and emits one output item per input item. Binary is preserved per option.

## User stories

- **As a workflow author**, I want to add a computed field `total = qty * price` to every item without a Code node.
- **As a workflow author**, I want to keep only a few fields and drop the rest before sending data to an integration.
- **As a workflow author**, I want to format or shift a date field into a target column.

## ADDED Requirements

### Requirement: Set / Edit Fields Node

A `set` node SHALL, for each input item, produce an output item whose `json` is the input `json` (or `{}` when `keep_only_set` is true) with each assignment `{name, value}` applied, where `value` is a literal or a `{{= ... }}` expression evaluated with `item` bound to the current item. A `fields_to_remove` list SHALL delete the named keys. Binary SHALL be carried when `include_binary` is true.

#### Scenario: Computed assignment

- **WHEN** an item is `{"qty": 3, "price": 10}` and the assignment is `{name: "total", value: "{{= item.json.qty * item.json.price }}"}`
- **THEN** the output item json SHALL be `{"qty": 3, "price": 10, "total": 30}`.

#### Scenario: Keep only set fields

- **WHEN** `keep_only_set` is true and the only assignment is `{name: "id", value: "{{= item.json.id }}"}` on item `{"id": 7, "junk": 1}`
- **THEN** the output item json SHALL be `{"id": 7}`.

#### Scenario: Remove a field

- **WHEN** `fields_to_remove` is `["secret"]` on item `{"id": 1, "secret": "x"}`
- **THEN** the output item json SHALL be `{"id": 1}`.

### Requirement: Rename Keys Node

A `rename_keys` node SHALL apply a list of `{from, to}` pairs to each item's json keys. When a `to` key already exists, the behaviour SHALL be overwrite unless `error_on_collision` is true, in which case the node fails.

#### Scenario: Simple rename

- **WHEN** the pair is `{from: "old", to: "new"}` on item `{"old": 5}`
- **THEN** the output item json SHALL be `{"new": 5}`.

#### Scenario: Collision errors when configured

- **WHEN** renaming `a -> b` on `{"a": 1, "b": 2}` with `error_on_collision: true`
- **THEN** the node SHALL fail with an error naming the colliding key `b`.

### Requirement: DateTime Node

A `datetime` node SHALL support `action ∈ {now, parse, format, add, subtract}` operating on a target `field`. `parse`/`format` SHALL use explicit format strings; `add`/`subtract` SHALL take a `{value, unit}` duration. The implementation SHALL reuse the expression engine's date helpers.

#### Scenario: Format a date field

- **WHEN** `action="format"`, `field="created"` holds an ISO datetime, and `format="%Y-%m-%d"`
- **THEN** the output item's `created` (or configured output field) SHALL be the date-only string.

#### Scenario: Add a duration

- **WHEN** `action="add"`, `field="ts"` is `2026-01-01T00:00:00Z`, duration `{value: 1, unit: "days"}`
- **THEN** the output field SHALL be `2026-01-02T00:00:00Z`.

## Out of Scope

- Multi-locale date formatting beyond strftime/strptime.
- Field-level type coercion DSL (use `set` + expressions).
