## 1. API key auth

- [x] 1.1 Add `ApiKey` SQLModel (`key_hash`, `prefix`, `last_used_at`, `revoked_at`, reserved `owner_id`)
- [x] 1.2 Key generation (`sk_…`) + `sha256` hashing via `secrets`/`hashlib`
- [x] 1.3 `require_api_key` FastAPI dependency (Bearer / `x-api-key`), update `last_used_at`
- [x] 1.4 Per-key in-process token-bucket rate limiter (`429` + `Retry-After`)
- [x] 1.5 Settings `RATE_LIMIT_PER_MIN=60`

## 2. Public v1 routers

- [x] 2.1 Create `app/routers/v1/` package guarded by `require_api_key`
- [x] 2.2 `POST /api/v1/run-task` (prompt+url → vision_navigate run)
- [x] 2.3 `POST /api/v1/workflows/{id}/run`
- [x] 2.4 `GET /api/v1/runs/{id}`, `GET /api/v1/runs` (paginated), `POST /api/v1/runs/{id}/cancel`
- [x] 2.5 `/api/v1/workflows` + `/api/v1/credentials` (masked) CRUD
- [x] 2.6 Add `{kind:"api", api_key_id}` to `Run.triggered_by`

## 3. OpenAPI

- [x] 3.1 Curate `/api/v1` schema (tags, examples, bearer auth scheme)
- [x] 3.2 Verify the document is sufficient for SDK generation

## 4. Frontend

- [x] 4.1 "API 密钥" Settings page (create reveal-once, name, revoke, last-used)
- [ ] 4.2 Link to interactive `/docs`

## 5. Tests

- [x] 5.1 Auth matrix (missing/invalid/revoked/valid; internal exempt)
- [x] 5.2 Reveal-once + revocation
- [x] 5.3 run-task creates + enqueues; cancel aborts
- [x] 5.4 Pagination + rate-limit 429
