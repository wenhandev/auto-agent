## Description

Array-level nodes that reshape the whole `input_items` array: `filter`, `sort`, `limit`, `aggregate`, `split_out`, and `remove_duplicates`. Expressions bind `item` to the item under consideration and `items` to the whole input. Each emits a possibly different-length `items` array; `output` is the first emitted item.

## User stories

- **As a workflow author**, I want to keep only in-stock products from a scraped list.
- **As a workflow author**, I want to sort results by price and keep the top 5.
- **As a workflow author**, I want to collapse a list of orders into a single total, or group them by customer.
- **As a workflow author**, I want to explode an array field into one item per element.

## ADDED Requirements

### Requirement: Filter Node

A `filter` node SHALL keep input items for which a `{{= ... }}` predicate (evaluated with `item` bound) is truthy, emitting the surviving items in order. A predicate evaluation error SHALL fail the node with a message including the offending item index.

#### Scenario: Keep matching items

- **WHEN** input items have json `[{"in":true},{"in":false},{"in":true}]` and the predicate is `"{{= item.json.in }}"`
- **THEN** the output SHALL be the two items with `in == true`, in order.

#### Scenario: Empty result

- **WHEN** no item satisfies the predicate
- **THEN** the output SHALL be an empty items array and `output` SHALL be `{}`.

### Requirement: Sort And Limit Nodes

A `sort` node SHALL order items by one or more `{field, order}` keys (path or expression), stably, with missing/None values ordered last deterministically. A `limit` node SHALL keep the first or last `count` items per `keep ∈ {first, last}`.

#### Scenario: Sort descending by field

- **WHEN** items have `price` values `[10, 30, 20]` and the key is `{field: "price", order: "desc"}`
- **THEN** the output order SHALL be `[30, 20, 10]`.

#### Scenario: Limit first N

- **WHEN** there are 7 items and `limit` has `keep="first"`, `count=5`
- **THEN** the output SHALL be the first 5 items.

### Requirement: Aggregate Node

An `aggregate` node SHALL support `operation ∈ {concat, sum, avg, min, max, count, group_by}` over a field. `concat` SHALL emit one item with the collected values list; numeric ops SHALL emit one item with the computed number; `count` SHALL emit the item count; `group_by` SHALL emit one item per distinct key with the grouped rows. A numeric op on a non-numeric value SHALL fail naming the field and value.

#### Scenario: Sum a field

- **WHEN** items have `amount` values `[10, 20, 30]` and `operation="sum"`, `field="amount"`
- **THEN** the output SHALL be a single item whose json contains the sum `60`.

#### Scenario: Group by key

- **WHEN** items are `[{c:"a",v:1},{c:"b",v:2},{c:"a",v:3}]`, `operation="group_by"`, `key="c"`
- **THEN** the output SHALL be one item for `c="a"` (grouping rows v=1,3) and one for `c="b"` (v=2).

#### Scenario: Numeric op on non-numeric fails

- **WHEN** `operation="sum"`, `field="name"`, and an item's `name` is `"abc"`
- **THEN** the node SHALL fail with an error naming `name` and the value `abc`.

### Requirement: Split Out Node

A `split_out` node SHALL explode an array `field` of each input item into one output item per element, merging the element (if a dict) into the carried json or wrapping it under an output field, per `include_other_fields`.

#### Scenario: Explode an array field

- **WHEN** an input item is `{"id": 1, "tags": ["x","y"]}`, `field="tags"`, output field `"tag"`
- **THEN** the output SHALL be two items: `{"id":1,"tag":"x"}` and `{"id":1,"tag":"y"}` (when `include_other_fields` is true).

### Requirement: Remove Duplicates Node

A `remove_duplicates` node SHALL drop items that duplicate earlier items on the comparison set (`compare ∈ {all_fields, selected_fields}` with `fields`), keeping the first occurrence.

#### Scenario: Dedupe on a key

- **WHEN** items are `[{id:1},{id:2},{id:1}]`, `compare="selected_fields"`, `fields=["id"]`
- **THEN** the output SHALL be `[{id:1},{id:2}]` (first occurrence of id=1 kept).

## Out of Scope

- Pivot/crosstab and multi-table joins (Merge `merge_by_key` covers join-by-key).
- Streaming aggregation over unbounded inputs (items are materialised + capped).
- Multi-key `group_by` in v1 (single key first).
