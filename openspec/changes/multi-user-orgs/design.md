## Context

`auto-agent-platform` deliberately reserved `owner_id` on every entity "so a later change can add multi-user support without a rewrite". This is that change. Skyvern is org-tenanted; we mirror the org-owns-resources, user-belongs-to-org model. The reserved columns make enforcement mechanical rather than a schema rewrite.

## Goals / Non-Goals

**Goals:**
- Users, organisations, roles, and enforced resource ownership.
- A safe first-boot: a seeded admin, not an open box.
- Zero-loss migration of existing single-user data into one org.

**Non-Goals:**
- Full SSO/SAML/OIDC (seam only).
- Billing/seats.
- Cross-org sharing / marketplace.
- Per-resource ACLs beyond org + role + workflow visibility.

## Decisions

### Decision 1: Org owns resources, user creates them
`owner_id` semantically becomes `org_id` (owning org) plus a `created_by` user. Enforcement is by org membership + role.
- **Why**: matches Skyvern's tenancy; sharing-within-team is the common need, not per-user silos.

### Decision 2: Sessions for the UI, org-scoped API keys for integrations
Email+password → httpOnly session cookie for the bundled UI; `/api/v1` keeps API keys, now `org_id`-scoped.
- **Why**: browsers want cookies; integrations want bearer keys. `public-api-and-auth` already built keys; we add org scoping.

### Decision 3: Cross-org access returns 404, not 403
Accessing another org's resource is indistinguishable from "does not exist".
- **Why**: avoids leaking resource existence across tenants.

### Decision 4: Roles owner/admin/member/viewer
Viewer reads; member runs/edits; admin manages members; owner manages the org.
- **Why**: the minimal useful role set; extends later without breaking.

### Decision 5: Bootstrap admin from env, never open
First boot creates a default org + an admin from `ADMIN_EMAIL`/`ADMIN_PASSWORD` (or a printed one-time password if unset). All routes require auth thereafter.
- **Why**: turning on multi-user must not leave the instance unauthenticated; a seeded admin is the safe default.

### Decision 6: Idempotent backfill of existing rows
A marker-guarded migration assigns every existing row to the default org and admin.
- **Why**: a working single-user install must keep working as a one-account org; same pattern as prior backfills.

## Risks / Trade-offs

- [Lockout: lost admin password] → documented reset via env on restart (re-seed if no users exist) / a CLI reset command.
- [Enforcement gap: a router forgets the org filter] → a shared dependency that injects the org filter; tests assert cross-org 404 on every list endpoint.
- [Migration assigns wrong owner] → single existing user ⇒ unambiguous; documented.
- [Password storage] → argon2/bcrypt; never plaintext; rate-limited login.
- [Breaking local UX] → the seeded admin auto-logs-in on localhost dev via the printed credentials; documented.

## Migration Plan

- `create_all` makes `user`/`organization`/`org_membership`.
- First boot: create default org + admin; backfill all rows to them (marker `.org_backfilled`).
- `ApiKey.org_id` added; existing keys assigned to the default org.
- New settings `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SESSION_SECRET`.

## Open Questions

- Auto-login on localhost for the single-user dev experience, or always show the login screen? (Lean: env flag `SINGLE_USER_MODE` that auto-authenticates the seeded admin, preserving today's friction-free local UX.)
- OIDC/SAML now or later? (Later; leave the IdP-subject column on `User`.)
