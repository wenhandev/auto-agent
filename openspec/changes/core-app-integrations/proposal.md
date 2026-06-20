## depends_on

- `integration-node-framework` — hard dependency. These apps are *descriptors* on that framework; this change ships no new executor code, only data descriptors + their credential types + fixtures.
- `items-data-model` — operations emit items.
- `per-workflow-credentials` — credential storage for each app's typed credential.

No browser dependency.

## Why

`integration-node-framework` builds the engine but ships zero apps. To make the framework useful — and to validate that "an app is just a descriptor" actually holds — we ship a small, curated set of high-value apps as the first descriptors. The chosen four cover the most common automation glue: team messaging, email, spreadsheets, and docs/DB. Each is the canonical proof that the framework's auth strategies (OAuth2 + API key) and response mapping (single/list/pagination) work end to end.

## What Changes

- **Ship four curated app descriptors** (proposed; confirm/adjust the list before implementation):
  - **Slack** (OAuth2): `chat.postMessage`, `conversations.list`, `conversations.history`, `users.list`, file upload.
  - **Gmail** (OAuth2): `messages.send`, `messages.list`, `messages.get`, `drafts.create`, `labels.list`.
  - **Google Sheets** (OAuth2): `spreadsheets.values.get`, `.append`, `.update`, `.clear`, `sheets.create`.
  - **Notion** (OAuth2 or internal-integration token): `pages.create`, `pages.retrieve`, `databases.query` (paginated), `blocks.children.append`, `databases.retrieve`.
- **One typed credential type per app** declaring its OAuth2 scopes/endpoints (or API-key fields), reusing the framework's auth injection and connect flow.
- **Response maps** for each operation: list operations declare `item_path` + pagination (Notion `databases.query` cursor; Gmail `messages.list` pageToken; Sheets ranges); single-object operations declare `root_path`.
- **Recorded fixtures** per operation so the descriptors are tested without live credentials, plus a thin live smoke checklist.
- **Planner catalogue entries** so natural-language requests ("post the summary to #ops in Slack") can resolve to `integration{app:"slack", resource:"chat", operation:"postMessage"}`.
- **Docs**: a short per-app setup note (which scopes, how to connect) surfaced in the credential UI.

## Capabilities

### New Capabilities

- `slack-integration`: the Slack descriptor, its OAuth2 credential type, operations, response maps, and fixtures.
- `gmail-integration`: the Gmail descriptor + credential + operations + fixtures.
- `google-sheets-integration`: the Sheets descriptor + credential + operations + fixtures.
- `notion-integration`: the Notion descriptor + credential + operations + fixtures.

### Modified Capabilities

- `chat-authoring` / `nl-workflow-planner`: the four apps are added to the planner's integration catalogue with usage hints.

## Impact

- **Backend**: four descriptor packages under `app/integrations/{slack,gmail,google_sheets,notion}/` (descriptor + credential type + optional custom hook for app-specific quirks like Slack's `ok:false` error envelope or Sheets' A1 range building) + recorded fixtures. ~150–250 LOC per app, mostly declarative data, + fixtures. Minimal executor code (only custom hooks where the declarative template cannot express a quirk).
- **Frontend**: none beyond what the framework's descriptor-driven UI already renders; app icons/labels added to a static asset map.
- **Runtime**: per-operation HTTP via the framework; OAuth2 connect per app.
- **Secrets**: OAuth tokens / API keys in the encrypted vault; descriptors hold no secrets.
- **Migration**: none beyond the framework's; descriptors are additive data.
- **Out of scope**: app *triggers* (incoming Slack events, Gmail push, Sheets change) — `polling-and-app-triggers`; the long tail of each app's full API surface (we ship the high-value operations, not parity with each provider); apps beyond the curated four (each future app is its own small descriptor change); a community/marketplace descriptor store.

## Decision needed

The four-app list (Slack, Gmail, Google Sheets, Notion) is a proposal. Confirm or substitute (e.g. Discord, Airtable, Telegram, HTTP-only webhooks, GitHub) before implementation begins; the framework treats them identically, so the list is cheap to change at spec time.
