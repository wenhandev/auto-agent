## depends_on

- `auto-agent-platform` — the existing routers (`workflows`, `runs`, `credentials`, `llm_config`, `triggers`, `chat`), the `Run` lifecycle, persistence.
- `vision-action-mode` (soft) — the `run_task` endpoint's "give a URL + prompt" shape is most useful once vision primitives exist; ships without it (it just creates a one-node workflow).

Consumed by `sdk-and-mcp` and `outbound-webhooks-hmac`.

## Why

Today the backend's endpoints are an *internal* surface for the bundled frontend: no authentication, no stability contract, ad-hoc shapes. Skyvern's product is, fundamentally, an **API**: "Full API for every capability — tasks, workflows, credentials, run status, cancellation, webhook replay. Build any integration programmatically", protected by an **API key**. To "做到和 Skyvern 一样" `auto-agent` needs a stable, versioned, authenticated public API surface and a `run_task` entry point that takes a prompt + URL.

## What Changes

- **API-key auth**: a new `ApiKey` SQLModel (`id`, `name`, `key_hash` (hashed, never stored plaintext), `prefix` (for display), `created_at`, `last_used_at`, `revoked_at`, reserved `owner_id`). A FastAPI dependency authenticates `Authorization: Bearer <key>` (or `x-api-key`) for all `/api/v1/...` routes. The bundled frontend keeps using a same-origin session/local path that is exempt (documented), so the UX is unchanged.
- **Versioned public surface** under `/api/v1`:
  - `POST /api/v1/run-task` — `{prompt, url?, data_schema?, browser_session_id?, browser_profile_id?, totp_identifier?, max_steps?}` → creates a one-node `vision_navigate` workflow (or attaches to a session) and returns a `run`. The Skyvern-style autonomous entry point.
  - `POST /api/v1/workflows/{id}/run` — `{parameters?, browser_session_id?, ...}` → enqueues a run of a saved workflow.
  - `GET /api/v1/runs/{id}` — run status + outputs; `GET /api/v1/runs` (list, paginated).
  - `POST /api/v1/runs/{id}/cancel` — cancel/abort a run.
  - `GET/POST /api/v1/workflows`, `GET/POST /api/v1/credentials` (masked) — programmatic CRUD parity with the UI.
  - `GET /api/v1/runs/{id}/artifacts` (from `run-artifacts-observability` when present).
- **OpenAPI**: FastAPI already emits `/openapi.json`; this change curates the `/api/v1` schema (tags, examples, auth scheme) so it is a usable contract for SDK generation.
- **Rate limiting (basic)**: a simple per-key in-process token bucket (single-process POC) with `429` + `Retry-After`.
- **UI**: a "API 密钥" Settings page to create (reveal-once), name, and revoke keys, plus a link to the interactive `/docs`.

## Capabilities

### New Capabilities

- `api-key-auth`: the `ApiKey` entity, hashed-key storage, the bearer/`x-api-key` auth dependency, reveal-once creation, revocation, `last_used_at` tracking, and the basic per-key rate limiter.
- `public-rest-api`: the versioned `/api/v1` surface (`run-task`, workflow run, run status/list/cancel, workflow + credential CRUD), curated OpenAPI, and pagination conventions.

### Modified Capabilities

- `run-history` (from `auto-agent-platform`): `POST /api/v1/run-task` and `.../cancel` are public, authenticated entry points to the existing run lifecycle; `Run.triggered_by` gains `{kind:"api", api_key_id}`.
- `platform-shell` (from `auto-agent-platform`): a new "API 密钥" Settings page.

## Impact

- **Backend**: new `app/routers/v1/` package mirroring internal routers behind the auth dependency; new `ApiKey` model + auth dependency + rate limiter; key hashing via `hashlib`/`secrets`. The internal frontend routes are kept and marked exempt. Tests: auth required/optional matrix, reveal-once, revocation, `run-task` creates+enqueues, cancel, pagination.
- **Frontend**: API-keys Settings page; otherwise the UI continues to use the internal path.
- **Runtime**: auth adds a hash compare per request; the rate limiter is in-memory.
- **Migration**: `create_all` makes `api_key`. `triggered_by` already JSON; add the `api` kind. No breaking change to internal routes.
- **Out of scope**: OAuth2 / user login (that's `multi-user-orgs`); scoped/permissioned keys per resource (keys are full-access in v1; scopes are a future change); distributed rate limiting (single-process only).
