## Description

A Slack app descriptor on the integration framework: an OAuth2 bot credential type and the operations `chat.postMessage`, `conversations.list`, `conversations.history`, `users.list`, `files.upload`. A custom hook maps Slack's `{ok:false}` envelope (returned with HTTP 200) to a node failure.

## User stories

- **As a workflow author**, I want to post a message to a channel as the final step of a workflow.
- **As a workflow author**, I want to list channels or fetch a channel's recent messages as items.
- **As an operator**, I want a Slack API logical error (`channel_not_found`) to fail the node clearly, not silently pass.

## ADDED Requirements

### Requirement: Slack OAuth2 Credential And Operations

The Slack descriptor SHALL declare an OAuth2 bot credential (authorize/token endpoints, scopes) using the framework's bearer injection, and SHALL expose `chat.postMessage`, `conversations.list`, `conversations.history`, `users.list`, and `files.upload`. List operations SHALL paginate via `response_metadata.next_cursor` and declare the correct `item_path`.

#### Scenario: Post a message

- **WHEN** an `integration{app:"slack", resource:"chat", operation:"postMessage"}` node runs with `channel` and `text` fields and a connected credential
- **THEN** it SHALL POST to `chat.postMessage` with a bearer token AND emit one item with the posted message object.

#### Scenario: List channels paginates

- **WHEN** `conversations.list` returns a `next_cursor` on page 1
- **THEN** the node SHALL fetch the next page and emit the concatenated `channels` as items (up to the cap).

### Requirement: Slack `ok:false` Maps To Failure

A custom hook SHALL inspect Slack's response envelope; when `ok` is false the node SHALL fail with an error containing Slack's `error` code.

#### Scenario: channel_not_found fails the node

- **WHEN** Slack returns HTTP 200 with `{"ok": false, "error": "channel_not_found"}`
- **THEN** the node SHALL fail with an error containing `"channel_not_found"`.

## Out of Scope

- Slack event subscriptions / slash commands (triggers — `polling-and-app-triggers`).
- The full Slack Web API surface beyond the listed operations.
