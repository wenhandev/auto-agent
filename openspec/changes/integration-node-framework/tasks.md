## 1. Shared contract (parent worker)

- [x] 1.1 `[shared-contract]` Author the descriptor schema models in `backend/app/integrations/schema.py` (`Field`, `RequestTemplate`, `ResponseMap`, `Pagination`, `Operation`, `Resource`, `IntegrationDescriptor`, `CredentialType`, `AuthSpec`).
- [x] 1.2 `[shared-contract]` Add `integration` to the `NodeType` literal; define `IntegrationParams {app, resource, operation, fields}`.
- [x] 1.3 `[shared-contract]` DB migration: add `type` column to credentials (default `generic`); add OAuth token storage (reserved vault fields or `oauth_tokens` table).
- [x] 1.4 `[shared-contract]` API contracts + TS mirrors: `GET /api/integrations`, `GET /api/integrations/{app}`, OAuth2 connect/callback; credential-type forms.
- [x] 1.5 `[shared-contract]` Smoke-check imports + migration + `tsc --noEmit`.

## 2. Registry + loader (Sibling A — `[backend-framework]`)

- [x] 2.1 Loader that reads `app/integrations/<app>/descriptor.(py|json)` into a validated registry at startup; fail with precise errors (unknown credential type, undeclared field reference).
- [x] 2.2 Catalogue endpoints `GET /api/integrations` and `GET /api/integrations/{app}`.
- [x] 2.3 Tests `backend/tests/test_integration_registry.py`: well-formed loads; unknown-cred and undeclared-field rejections; catalogue shape.

## 3. HTTP client extraction (Sibling A continued — `[backend-framework]`)

- [x] 3.1 Extract `app/nodes/_http_client.py` from `http_request` (timeout/retry/backoff/redirect/SSRF/error-map); make `http_request` a thin wrapper (no behaviour change).
- [x] 3.2 Regression test that `http_request` behaviour is unchanged (reuse its existing tests).

## 4. Generic executor (Sibling A continued — `[backend-framework]`)

- [x] 4.1 `app/nodes/integration.py`: validate fields; render request against `$fields`/`$cred`/`nodes`/`item`/`items`; inject auth; execute via `_http_client`; map response→items per `ResponseMap`; paginate to caps.
- [x] 4.2 Secret-redaction tagging in the renderer; redact in events.
- [x] 4.3 Tests `backend/tests/test_integration_executor.py` (recorded fixtures): list→N items; single→1 item; missing required field; HTTP 500 mapping; 2-page pagination; cap truncation; auth-header redaction.

## 5. Typed credentials + OAuth2 (Sibling B — `[backend-auth]`)

- [x] 5.1 Credential-type registry + the `generic` back-compat type; typed credential instance storage with `type`.
- [x] 5.2 Auth injectors: `api_key_header`/`api_key_query`/`bearer`/`basic`/`none`.
- [x] 5.3 OAuth2 connect (`/api/oauth2/{app}/connect`), signed `state`, `/callback` token exchange, vault storage; lazy refresh before bearer injection with a per-credential lock.
- [x] 5.4 Tests `backend/tests/test_typed_credentials.py`: generic back-compat; each injector; OAuth2 connect stores tokens; expired token refreshed; bad-state callback rejected.

## 6. Frontend (Sibling C — `[frontend]`)

- [x] 6.1 Descriptor-driven `integration` node form: resource→operation→fields generated from the descriptor; fetch catalogue + descriptor.
- [ ] 6.2 Credential-type forms generated from `CredentialType.fields`; masked secret inputs.
- [ ] 6.3 "Connect <app>" OAuth2 flow UI (initiate + handle return).
- [ ] 6.4 Smoke-check: `npm run build`; configure a fixture app, fill an operation, run it.

## 7. Verification (parent worker)

- [x] 7.1 `[verification]` With a recorded fixture app: an `integration` node runs a list operation, emits one item per record, and pagination accumulates pages.
- [x] 7.2 `[verification]` API-key and bearer injection appear in the request and are redacted in events.
- [x] 7.3 `[verification]` OAuth2 connect + a run that triggers a lazy refresh.
- [x] 7.4 `[verification]` Existing untyped credential still resolves via `{{cred...}}`.
- [ ] 7.5 `[verification]` Kill all dev processes.

---

## Parallel Implementation Plan

### Sibling A — Framework core `[backend-framework]`
**Owns.** `app/integrations/schema.py` (after §1), loader/registry, catalogue endpoints, `_http_client` extraction, `app/nodes/integration.py`, executor tests.
**Must NOT touch.** Auth/OAuth modules (Sibling B), frontend.

### Sibling B — Typed credentials + OAuth2 `[backend-auth]`
**Owns.** Credential-type registry, auth injectors, OAuth2 routes + refresh, credential tests, the credentials migration.
**Must NOT touch.** The descriptor executor internals (consume the injector interface only), frontend.

### Sibling C — Frontend `[frontend]`
**Owns.** Descriptor-driven node form, credential-type forms, OAuth connect UI, TS mirrors.
**Must NOT touch.** Backend.

**Shared contract deps (§1).** Descriptor + credential-type models, `integration` node type, migration, API contracts. Interface seam between A and B: the `AuthInjector.inject(request, credential_instance)` protocol.
