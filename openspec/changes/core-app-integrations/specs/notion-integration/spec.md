## Description

A Notion app descriptor on the framework: a credential type supporting OAuth2 and/or an internal-integration token, with the required `Notion-Version` header injected. Operations: `pages.create`, `pages.retrieve`, `databases.query`, `blocks.children.append`, `databases.retrieve`.

## User stories

- **As a workflow author**, I want to create a Notion page or append blocks from workflow data.
- **As a workflow author**, I want to query a database and get one item per row, following pagination.
- **As a solo operator**, I want to connect with a simple internal-integration token, not full OAuth2.

## ADDED Requirements

### Requirement: Notion Credential And Required Version Header

The Notion descriptor SHALL declare a credential type supporting OAuth2 and an internal-integration token (bearer injection), and SHALL inject the required `Notion-Version` header on every request.

#### Scenario: Version header injected

- **WHEN** any Notion operation runs
- **THEN** the request SHALL include a `Notion-Version` header from the descriptor.

#### Scenario: Internal token connects without OAuth

- **WHEN** an operator provides an internal-integration token credential
- **THEN** operations SHALL authenticate via bearer without an OAuth2 connect flow.

### Requirement: Notion Operations And Database Query Pagination

The descriptor SHALL expose `pages.create`, `pages.retrieve`, `databases.query`, `blocks.children.append`, `databases.retrieve`. `databases.query` SHALL paginate via `next_cursor`/`has_more` with `item_path = "results"`; `pages.create`/`pages.retrieve` SHALL emit one item (`root_path`).

#### Scenario: Query a database paginates

- **WHEN** `databases.query` returns `has_more: true` with a `next_cursor`
- **THEN** the node SHALL fetch the next page and emit the concatenated `results` as items up to the cap.

#### Scenario: Create a page emits the page

- **WHEN** `pages.create` succeeds
- **THEN** the node SHALL emit one item with the created page object.

## Out of Scope

- Notion webhooks / change triggers.
- Block-level rich-text builders beyond a basic mapping in v1.
