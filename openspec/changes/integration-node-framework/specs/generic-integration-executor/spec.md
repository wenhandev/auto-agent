## Description

The `integration` node executes any descriptor operation: it validates the node's `fields`, renders the declarative request (with token/expression interpolation and credential auth injection), executes it via the shared `http_client`, and maps the response into output `items` per the operation's `ResponseMap`, iterating pagination up to caps.

## User stories

- **As a workflow author**, I want to drop one `integration` node, pick app/resource/operation, fill fields, and get records as items.
- **As a workflow author**, I want a paginated list operation to return all pages (up to a cap) as a flat item array.
- **As an operator**, I want HTTP errors mapped to a clear node failure, with secrets redacted in the run log.

## ADDED Requirements

### Requirement: Generic Operation Execution

The `integration` node SHALL accept `{app, resource, operation, fields}`, resolve the descriptor operation from the registry, validate `fields` against the operation's `Field[]` (required/kind/options), render the request template against a namespace exposing `$fields`, `$cred`, `nodes`, `item`, `items`, execute it via the shared `http_client`, and emit output `items` per the `ResponseMap`.

#### Scenario: List operation emits one item per record

- **WHEN** an operation's `response.item_path` resolves to an array of 3 records
- **THEN** the node SHALL emit 3 items, one per record's json.

#### Scenario: Single-object operation emits one item

- **WHEN** an operation declares `root_path` (single object result)
- **THEN** the node SHALL emit exactly one item.

#### Scenario: Missing required field fails

- **WHEN** a required field is absent from the node's `fields`
- **THEN** the node SHALL fail with an error naming the missing field, before any HTTP call.

### Requirement: Shared HTTP Transport Reuse

The integration executor SHALL execute requests through the same `http_client` used by `http_request` (timeout, retry/backoff, redirect policy, SSRF guard, HTTP-error→message mapping). It SHALL NOT reimplement transport behaviour.

#### Scenario: HTTP 500 mapped to node failure

- **WHEN** the provider returns HTTP 500 after the configured retries
- **THEN** the node SHALL fail with an error consistent with `http_request`'s error mapping.

### Requirement: Pagination Accumulation

When `response.pagination` is set, the executor SHALL iterate pages (cursor/offset/link-header per the descriptor) and concatenate items, stopping at `max_pages` or `max_items_per_node`, whichever comes first.

#### Scenario: Two-page cursor pagination

- **WHEN** page 1 returns 2 records and a next cursor, and page 2 returns 1 record and no cursor
- **THEN** the node SHALL emit 3 items total.

#### Scenario: Cap stops pagination

- **WHEN** pagination would exceed `max_pages`
- **THEN** the executor SHALL stop at the cap and the node SHALL surface that the result was truncated.

### Requirement: Secret Redaction In Events

Values originating from secret credential fields or auth injection SHALL be redacted (`"***"`) in run events and debug logs.

#### Scenario: Auth header redacted

- **WHEN** a bearer token is injected into the `Authorization` header
- **THEN** the `node_completed`/debug event SHALL show `Authorization: ***`, never the token.

## Out of Scope

- App triggers/webhooks (`polling-and-app-triggers`).
- Non-REST transports.
