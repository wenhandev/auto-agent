## Context

`REFERENCES.md` Cross-cutting theme #5 ("Credentials are pluggable, never built-in") names Skyvern's 8-backend `parameter.py` and warns the single-backend assumption locks in the moment a non-browser node resolves a secret. We introduce the strategy interface before that happens, keeping the Fernet vault as the default backend so nothing changes for current users.

## Goals / Non-Goals

**Goals:**
- A clean `CredentialBackend` interface with the local vault as one implementation.
- Namespaced tokens so a workflow can pull from a specific backend.
- Backward compatibility: unprefixed `{{cred.name.field}}` keeps resolving to the default (local) backend.

**Non-Goals:**
- Implementing every conceivable backend now (AWS/HashiCorp deferred; same interface).
- Write-through to read-only backends.
- Secret rotation / lifecycle management.

## Decisions

### Decision 1: ABC with explicit `capabilities`
`CredentialBackend` declares which ops it supports (`read`, `write`, `delete`, `list`). The UI and resolver consult capabilities rather than try/except.
- **Why**: read-only backends (Bitwarden/1Password/Azure) are first-class; the create form hides for them cleanly.

### Decision 2: Namespaced tokens, default backend for unprefixed
`{{cred.bw:github.password}}` selects the `bw` mount; `{{cred.github.password}}` uses the default. The namespace is the *mount name*, not the backend type, so two Bitwarden vaults can coexist.
- **Why**: explicit selection without breaking existing tokens; mounts decouple name from type.
- **Alternative rejected**: a single flat namespace with name collisions across backends (ambiguous, dangerous).

### Decision 3: Backend config encrypted with the local Fernet key (bootstrap)
Connection settings (API tokens, vault URLs) for external backends are themselves stored encrypted by the `local` backend's Fernet key.
- **Why**: avoids a chicken-and-egg; the local key is the root of trust already.

### Decision 4: CLI adapters via subprocess, HTTP adapters via httpx
`bitwarden`/`onepassword` shell out to `bw`/`op` (already the operator's installed tooling); `azure_key_vault` uses the SDK; `http_vault` uses `httpx`.
- **Why**: CLIs handle the vendor auth dance (unlock, session tokens) better than re-implementing it; SDK for Azure is well-supported.
- **Alternative rejected**: re-implementing Bitwarden/1Password auth protocols (large, fragile).

### Decision 5: Per-run resolution cache
A name resolved once during a run is cached for that run.
- **Why**: external backends add latency; a `foreach` over 100 items must not hit the vault 100×.

### Decision 6: Link table keys on namespaced identity
`per-workflow-credentials` links reference `<mount>:<name>` so enforcement is unambiguous across backends.
- **Why**: a workflow scoped to `bw:github` should not implicitly allow `local:github`.

## Risks / Trade-offs

- [External backend down / locked] → resolution fails the node with an actionable error naming the mount; "测试连接" surfaces it at config time.
- [Subprocess CLI not installed] → adapter capability probe fails fast; Settings shows "未检测到 bw CLI".
- [Latency under foreach] → per-run cache + the recommendation to use `local` for hot secrets.
- [Backward-compat break] → unprefixed tokens explicitly route to default; covered by tests.

## Migration Plan

- Wrap the existing vault as `local`; register it as the default mount on first boot.
- Existing tokens/links resolve unchanged (default mount).
- New `credential_backend_config` table via `create_all`. External adapters are opt-in via Settings.

## Open Questions

- Should the `local` mount be renameable/removable? (Lean: always present, default, not removable.)
- Cache TTL within a long-lived `browser-session`-bound run? (Lean: per-run cache only; sessions don't extend it.)
