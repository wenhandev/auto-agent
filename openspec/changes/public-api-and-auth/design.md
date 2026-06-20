## Context

The platform exposes internal routers consumed by the bundled React app over same-origin requests. To support programmatic integrations and SDKs (and to align with Skyvern's API-first identity) we add an authenticated, versioned public surface without disrupting the existing UI.

## Goals / Non-Goals

**Goals:**
- A stable `/api/v1` contract suitable for SDK generation.
- API-key auth that never stores plaintext keys.
- A Skyvern-style `run-task` autonomous entry point.

**Non-Goals:**
- User accounts / OAuth (→ `multi-user-orgs`).
- Per-resource key scopes (v1 keys are full-access).
- Distributed rate limiting.

## Decisions

### Decision 1: Separate `/api/v1` routers, internal routes stay
`/api/v1/*` is the public, authed, versioned surface; the existing `/api/*` internal routes remain for the bundled frontend and are exempt from key auth (same-origin).
- **Why**: don't destabilise the UI; give integrators a clean contract. Versioning lets the internal surface evolve faster than the public one.
- **Alternative rejected**: retrofitting auth onto all existing routes (breaks the no-auth local UX and couples UI churn to the public contract).

### Decision 2: Store only a key hash + prefix
On creation, generate `sk_<random>`; store `sha256(key)` and a display prefix (`sk_live_abc…`); return the full key once.
- **Why**: a DB leak must not expose usable keys; reveal-once is the standard.

### Decision 3: `run-task` creates an ephemeral one-node workflow
`POST /api/v1/run-task` builds a `vision_navigate` node from `{prompt,url}`, persists a lightweight workflow (or a not-persisted ephemeral run when `persist=false`), and enqueues it.
- **Why**: mirrors Skyvern's `runTask({prompt,url,...})`; reuses the whole executor/run pipeline.

### Decision 4: Auth as a FastAPI dependency, exempt list for internal
A `require_api_key` dependency reads `Authorization: Bearer` or `x-api-key`, hashes, looks up a non-revoked key, updates `last_used_at`. Internal routes don't include it.
- **Why**: declarative, testable, centralised.

### Decision 5: In-process token-bucket rate limit
Per-key bucket (`RATE_LIMIT_PER_MIN`, default 60) returning `429 + Retry-After`.
- **Why**: protects the single Chromium from API stampedes; honest about single-process scope.

## Risks / Trade-offs

- [Key leakage] → hashed storage, reveal-once, revocation, `last_used_at` for anomaly spotting.
- [Internal routes unauthed] → bound to same-origin/loopback by deployment guidance; documented that exposing the box publicly requires fronting `/api` too.
- [run-task abuse] → rate limit + the executor's single-run queue naturally serialise; `concurrent-runs-browser-pool` will add real parallelism with its own caps.
- [Contract drift] → `/api/v1` is frozen-ish; breaking changes go to `/api/v2`.

## Migration Plan

- `create_all` makes `api_key`.
- Add the `api` kind to `Run.triggered_by`.
- New settings `RATE_LIMIT_PER_MIN=60`. No change to existing routes.

## Open Questions

- Should `/api/v1` fully supersede the internal routes eventually (UI migrates to v1 + a session token)? (Lean: yes, long-term; out of scope now.)
- Idempotency keys on `run-task` to dedupe retried POSTs? (Lean: add `Idempotency-Key` header support; defer to a follow-up.)
