## Description

A Gmail app descriptor on the framework: a Google OAuth2 credential type and the operations `messages.send`, `messages.list`, `messages.get`, `drafts.create`, `labels.list`. A custom hook builds the base64url RFC822 MIME for sends from friendly fields.

## User stories

- **As a workflow author**, I want to send an email with to/subject/body fields without hand-building MIME.
- **As a workflow author**, I want to list and fetch messages as items.

## ADDED Requirements

### Requirement: Gmail OAuth2 Credential And Operations

The Gmail descriptor SHALL declare a Google OAuth2 credential (gmail send/modify scopes, bearer injection) and expose `messages.send`, `messages.list`, `messages.get`, `drafts.create`, `labels.list`. `messages.list` SHALL paginate via `pageToken`; `messages.get` SHALL emit one item (`root_path`).

#### Scenario: Send an email from friendly fields

- **WHEN** a `messages.send` node runs with `to`, `subject`, `body` fields
- **THEN** the custom hook SHALL build a base64url RFC822 message AND the node SHALL emit one item with the sent message id/threadId.

#### Scenario: List messages paginates

- **WHEN** `messages.list` returns a `nextPageToken`
- **THEN** the node SHALL fetch subsequent pages and emit the concatenated `messages` as items up to the cap.

## Out of Scope

- Gmail push notifications / watch (triggers).
- Attachments handling beyond a basic inline body in v1 (binary attachments are a fast-follow).
