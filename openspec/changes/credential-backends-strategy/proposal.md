## depends_on

- `auto-agent-platform` — `credential-vault` (the current single Fernet backend, the `Credential` entity, lookup-by-name, the masker).
- `per-workflow-credentials` — the link table + resolution enforcement that must keep working across backends.

Soft synergy with `totp-2fa-automation` (a backend may itself store TOTP secrets) and `expanded-node-library` (`send_email` / `http_request` are where the single-backend assumption first hurts).

## Why

`auto-agent` has exactly **one** credential backend: the local Fernet vault. Skyvern supports the native encrypted store **plus** Bitwarden, 1Password, Azure Key Vault, and a **custom HTTP vault**. `ROADMAP.md` already flags this as the moment-of-no-return: the single-backend assumption hardens the instant `send_email`/`http_request` start resolving secrets, and retrofitting a strategy interface later is a rewrite. We re-spec the credential layer as a **pluggable backend strategy** now, with the existing Fernet vault as the default `local` backend, before more code couples to it.

## What Changes

- **Strategy interface** `app/services/credential_backends/base.py`: a `CredentialBackend` ABC with `get(name) -> CredentialFields`, `list() -> list[CredentialRef]`, `put(name, fields)` (optional; some backends are read-only), `delete(name)` (optional), and `capabilities` (which ops are supported, whether writes are allowed).
- **Backends**:
  - `local` (default): the existing Fernet vault, wrapped behind the interface. Behaviour-preserving.
  - `env`: read-only, resolves from environment variables by a name prefix (`AUTOAGENT_CRED_<NAME>_<FIELD>`).
  - `bitwarden`: via the Bitwarden CLI (`bw`) or HTTP API; read-mostly.
  - `onepassword`: via the 1Password CLI (`op`) / Connect; read-mostly.
  - `azure_key_vault`: via `azure-keyvault-secrets` + `DefaultAzureCredential`; read-mostly.
  - `http_vault`: a generic custom HTTP vault — configurable URL + auth header; `GET {url}/{name}` returns the fields JSON.
- **Backend registry + config**: a `CredentialBackendConfig` table (or rows reusing `LlmConfig`-style activation) selects the active backend(s) and holds their connection settings (themselves encrypted by the local Fernet key — bootstrap secret). Multiple backends can be **mounted under namespaces** (`local:`, `bw:`, `op:`) so `{{cred.bw:github-token.password}}` selects a backend explicitly; an unprefixed name resolves against the default backend.
- **Resolution**: `credential_interpolation.resolve_params` routes `{{cred.<ns?>:<name>.<field>}}` to the right backend via the registry. Per-workflow link enforcement is preserved — the link table keys on the namespaced credential reference.
- **UI**: a "凭据后端" section in Settings to mount/test backends (with a "测试连接" button) and pick the default; the credential create form is available only for write-capable backends (`local`); read-only backends show a discovered list.

## Capabilities

### New Capabilities

- `credential-backend-strategy`: the `CredentialBackend` ABC, the backend registry, namespaced resolution, the backend config + activation, and the Settings UI to mount/test/select backends.
- `credential-backend-adapters`: the concrete `local` / `env` / `bitwarden` / `onepassword` / `azure_key_vault` / `http_vault` adapters and their capability declarations.

### Modified Capabilities

- `credential-vault` (from `auto-agent-platform`): the vault becomes the `local` backend behind the strategy interface; direct callers go through the registry. Token syntax extends from `{{cred.<name>.<field>}}` to optionally-namespaced `{{cred.<ns>:<name>.<field>}}` (unprefixed = default backend; fully backward compatible).
- `workflow-credential-link` (from `per-workflow-credentials`): the link references a namespaced credential identity so a workflow can be scoped to specific backend entries.

## Impact

- **Backend**: new `app/services/credential_backends/` package (base + adapters + registry). Optional dependencies added lazily/extra-only (`azure-keyvault-secrets`; CLIs `bw`/`op` invoked as subprocesses). New config table. Resolver routing change. Tests: registry routing, namespaced tokens, link enforcement across backends, each adapter behind a fake transport.
- **Frontend**: Settings "凭据后端" mount/test/select; create-form gating by write capability.
- **Runtime**: external backends add network/subprocess latency on resolution; a short per-run cache (already resolved names) avoids repeated lookups within one run.
- **Migration**: existing credentials are the `local` backend's contents — zero data migration; unprefixed tokens keep resolving to `local`. New config table via `create_all`.
- **Out of scope**: AWS Secrets Manager + HashiCorp Vault adapters (additive later, same interface); write-through to read-only backends; secret rotation orchestration; backend-side audit logs.
