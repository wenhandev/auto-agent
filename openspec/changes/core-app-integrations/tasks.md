## 0. Confirm scope (parent worker)

- [x] 0.1 Confirm the four-app list (Slack, Gmail, Google Sheets, Notion) with the user; swap any (e.g. Airtable/Discord/Telegram/GitHub) before building. Each app is an independent capability, so swaps are cheap.

## 1. Shared scaffolding (parent worker)

- [x] 1.1 `[shared-contract]` Create `app/integrations/{slack,gmail,google_sheets,notion}/` packages with `descriptor.py`, `credential.py`, optional `custom.py`, and `fixtures/`.
- [x] 1.2 `[shared-contract]` Add a shared Google OAuth2 base (endpoints/client config) reused by Gmail + Sheets credential types.
- [ ] 1.3 `[shared-contract]` Add app icon/label entries to the frontend static asset map.
- [ ] 1.4 `[shared-contract]` Per-app `LIVE_SMOKE.md` checklist stubs.

## 2. Slack (Sibling A — `[integration-app]`)

- [x] 2.1 OAuth2 bot credential type (scopes, endpoints).
- [x] 2.2 Operations `chat.postMessage`, `conversations.list`, `conversations.history`, `users.list`, `files.upload` with response maps + cursor pagination.
- [x] 2.3 `custom.py` hook mapping `{ok:false}` → node failure naming `error`.
- [x] 2.4 Recorded fixtures + tests: post message; list channels (paginated); `ok:false` failure.

## 3. Gmail (Sibling B — `[integration-app]`)

- [x] 3.1 Google OAuth2 credential type (gmail scopes) on the shared base.
- [x] 3.2 Operations `messages.send`, `messages.list`, `messages.get`, `drafts.create`, `labels.list`; `pageToken` pagination.
- [x] 3.3 `custom.py` hook building base64url RFC822 MIME from to/subject/body.
- [x] 3.4 Recorded fixtures + tests: send (MIME built); list (paginated); get (single item).

## 4. Google Sheets (Sibling C — `[integration-app]`)

- [x] 4.1 Google OAuth2 credential type (spreadsheets scope) on the shared base.
- [x] 4.2 Operations `values.get`, `values.append`, `values.update`, `values.clear`, `spreadsheets.create`.
- [x] 4.3 `custom.py` hooks: A1 range building; rows↔objects via header row (`as_objects`).
- [x] 4.4 Recorded fixtures + tests: append rows; read range as objects; raw matrix mode.

## 5. Notion (Sibling D — `[integration-app]`)

- [x] 5.1 Credential type supporting OAuth2 + internal-integration token; inject `Notion-Version` header.
- [x] 5.2 Operations `pages.create`, `pages.retrieve`, `databases.query`, `blocks.children.append`, `databases.retrieve`; `next_cursor`/`has_more` pagination.
- [x] 5.3 Recorded fixtures + tests: create page (single item); database query (paginated); version header present; internal-token auth path.

## 6. Planner catalogue + docs (parent worker)

- [ ] 6.1 Add the four apps to the planner's integration catalogue with usage hints (e.g. "post to Slack" → slack/chat/postMessage).
- [ ] 6.2 Per-app setup note (scopes, how to connect) surfaced in the credential UI.
- [ ] 6.3 Substring regression test for the catalogue additions.

## 7. Verification (parent worker)

- [x] 7.1 `[verification]` Fixture-only CI: every operation passes against its recorded fixture.
- [ ] 7.2 `[verification]` Planner: "post a summary to #ops in Slack" resolves to the Slack postMessage integration node.
- [ ] 7.3 `[verification]` Manual live smoke per `LIVE_SMOKE.md` for at least Slack + one Google app (connect, one send, one list).
- [ ] 7.4 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

Four independent sibling workers, one per app — each owns its `app/integrations/<app>/` package and fixtures only and must NOT touch other apps, the framework core, or the frontend (beyond the shared asset map landed in §1). The parent lands §1 scaffolding + the Google OAuth2 base first, then the planner catalogue + docs (§6) after the apps exist.

- **Sibling A** — Slack `[integration-app]`
- **Sibling B** — Gmail `[integration-app]`
- **Sibling C** — Google Sheets `[integration-app]`
- **Sibling D** — Notion `[integration-app]`

**Shared contract deps (§1).** App package scaffolding, the shared Google OAuth2 base (Gmail + Sheets), the frontend asset map. All app behaviour rides on `integration-node-framework`; no new executor code beyond per-app `custom.py` hooks.
