## 1. Identity model

- [x] 1.1 Add `User`, `Organization`, `OrgMembership` SQLModels (roles owner/admin/member/viewer)
- [x] 1.2 Password hashing (argon2/bcrypt); add dependency
- [x] 1.3 Add `org_id` to `ApiKey`; `created_by`/`org_id` semantics on owned entities
- [x] 1.4 Settings `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SESSION_SECRET`, `SINGLE_USER_MODE`

## 2. AuthN

- [x] 2.1 Email+password login → httpOnly session token; logout
- [x] 2.2 Rate-limited login attempts
- [x] 2.3 Bootstrap admin + default org on first boot (env or printed OTP)
- [x] 2.4 Org-scoped API keys; rate limiter keyed per org

## 3. AuthZ

- [ ] 3.1 Central authz layer (membership + role checks)
- [x] 3.2 Shared dependency injecting the org filter into list/read/write
- [x] 3.3 Cross-org access → 404; enforce on every owned router
- [ ] 3.4 `Workflow.visibility ∈ {private, org}` enforcement

## 4. Migration

- [x] 4.1 Idempotent backfill: assign all existing rows to default org/admin (marker `.org_backfilled`)
- [x] 4.2 Assign existing API keys to the default org
- [ ] 4.3 `SINGLE_USER_MODE` auto-auth path

## 5. Frontend

- [x] 5.1 Login screen + logout
- [x] 5.2 "组织与成员" Settings (invite by email, set roles)
- [ ] 5.3 Org switcher; all resource lists scoped to current org

## 6. Tests

- [ ] 6.1 Role permission matrix
- [x] 6.2 Cross-org isolation (404) on every list endpoint
- [x] 6.3 Bootstrap admin; backfill idempotency
- [x] 6.4 Org-scoped API keys + per-org rate limiting
