## depends_on

- `auto-agent-platform` — the reserved `owner_id` columns, all entity tables, persistence.
- `public-api-and-auth` — API keys become user/org-scoped; the auth dependency is extended to carry identity.
- `per-workflow-credentials` — per-workflow scoping is the enforcement seam this change builds org-level ACLs on.

No hard dependency on other in-flight changes; soft synergy with everything that has a reserved `owner_id`.

## Why

`auto-agent` is single-user by construction, but every major entity already reserves an `owner_id` "so a later change can add multi-user support without a rewrite" (`auto-agent-platform`). Skyvern is multi-tenant: organisations own workflows, credentials, and runs, and **share across a team**. To "做到和 Skyvern 一样" as a real platform (not just locally), `auto-agent` needs users, organisations, and resource ownership/sharing. This change activates the reserved seam.

## What Changes

- **Identity**: a `User` SQLModel (`id`, `email`, `password_hash` or external-IdP subject, `name`, `created_at`, `disabled_at`) and an `Organization` SQLModel (`id`, `name`, `created_at`), with `OrgMembership` (`user_id`, `org_id`, `role ∈ {owner, admin, member, viewer}`).
- **AuthN**: email+password login issuing a session token (httpOnly cookie for the UI) plus the existing API keys, which become **org-scoped** (`ApiKey.org_id`). A bootstrap admin is created on first boot from env (`ADMIN_EMAIL`/`ADMIN_PASSWORD`) so the box is never wide-open.
- **AuthZ**: `owner_id` on every owned entity is populated and **enforced** (it becomes `org_id` semantically — owned by an org, created_by a user). A central authorization layer gates reads/writes by org membership + role. Viewers read; members run/edit; admins manage members; owners manage the org.
- **Resource scoping**: `GET` lists are filtered to the caller's org; cross-org access is denied (404, not 403, to avoid existence leaks). Credentials, workflows, runs, triggers, profiles, sessions, webhooks, and API keys are all org-scoped.
- **Sharing**: workflows can be shared **within** an org by role; an optional `Workflow.visibility ∈ {private, org}` controls whether non-owners in the org can see/run it.
- **Migration of existing single-user data**: on first boot after this change, a default org + the bootstrap admin are created and **all existing rows are assigned to that org/user** (idempotent backfill, marker file), so a single-user install keeps working with one seeded account.
- **UI**: a login screen; an "组织与成员" Settings area (invite by email, set roles); resource lists scoped to the current org; an org switcher when a user belongs to several.

## Capabilities

### New Capabilities

- `user-identity-auth`: `User`/`Organization`/`OrgMembership` entities, email+password (or IdP subject) login, session tokens, the bootstrap admin, and org-scoped API keys.
- `org-authorization`: the central authz layer (membership + role checks), `owner_id`/`org_id` enforcement on every owned entity, cross-org denial, and workflow `visibility`.
- `single-user-migration`: the first-boot default-org + admin creation and the idempotent assignment of all existing rows.

### Modified Capabilities

- `api-key-auth` (from `public-api-and-auth`): keys gain `org_id`; the auth dependency resolves identity + org and the rate limiter keys per org.
- `workflow-persistence` / `credential-vault` / `run-history` / `workflow-triggers` / `browser-sessions` / `outbound-webhooks` (across changes): every owned entity's `owner_id`/`org_id` is enforced; list endpoints filter by org.
- `platform-shell` (from `auto-agent-platform`): adds login, org/member management, and an org switcher.

## Impact

- **Backend**: new identity/org tables + authz layer + login routes + session handling; an enforcement pass across all routers (the `owner_id` seam makes this mechanical). Password hashing via `argon2`/`bcrypt` (new dependency). Tests: role matrix, cross-org isolation (404), bootstrap admin, backfill idempotency, org-scoped API keys + rate limiting.
- **Frontend**: login screen, org/member admin, org switcher, all lists scoped to org. Moderate.
- **Runtime**: an authz check per request (membership lookup, cached per session); negligible.
- **Migration**: `create_all` makes the identity tables; the idempotent backfill assigns existing rows to the default org/admin (marker `backend/.org_backfilled`, same pattern as prior backfills). Existing local installs become a one-account org with no behaviour change.
- **Out of scope**: full SSO/SAML/OIDC (a `sso-integration` follow-up; this change leaves an IdP-subject seam); fine-grained per-resource ACLs beyond org+role+visibility; billing/seats; audit logs (a `audit-log` follow-up); cross-org sharing/marketplace.
