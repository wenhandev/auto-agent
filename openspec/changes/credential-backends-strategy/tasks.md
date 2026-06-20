## 1. Strategy interface & registry

- [x] 1.1 Create `app/services/credential_backends/base.py` (`CredentialBackend` ABC + `capabilities`)
- [x] 1.2 Create the backend registry with named mounts + default mount
- [ ] 1.3 Add `credential_backend_config` table (encrypted connection settings)
- [x] 1.4 Per-run resolution cache

## 2. Adapters

- [x] 2.1 `local` adapter wrapping the Fernet vault (behaviour-preserving), registered as default
- [x] 2.2 `env` adapter (read-only, prefix-based)
- [ ] 2.3 `bitwarden` adapter (CLI/API, capability probe)
- [ ] 2.4 `onepassword` adapter (CLI/API, capability probe)
- [ ] 2.5 `azure_key_vault` adapter (SDK, optional dependency)
- [x] 2.6 `http_vault` adapter (httpx, configurable URL + auth header)
- [x] 2.7 `vault` stub adapter (`NotImplementedError` / injectable mock for tests)

## 3. Resolution

- [x] 3.1 Extend token grammar to `{{cred.<mount>:<name>.<field>}}` (unprefixed = default)
- [x] 3.2 Route resolution through the registry
- [x] 3.3 Key per-workflow links on namespaced identity; enforce (local mount via existing link table)
- [x] 3.4 Tests: routing, namespaced tokens, backward-compat default, link enforcement, fake-transport adapters

## 4. Frontend

- [ ] 4.1 Settings "凭据后端" mount/configure section
- [ ] 4.2 "测试连接" capability probe per backend
- [ ] 4.3 Default-backend selector
- [ ] 4.4 Gate the credential create form by `write` capability; show discovered list for read-only

## 5. Migration

- [x] 5.1 Register `local` as default mount on first boot; existing tokens/links unchanged
- [x] 5.2 Backend selection via `CREDENTIAL_BACKEND=local|env|vault` setting
