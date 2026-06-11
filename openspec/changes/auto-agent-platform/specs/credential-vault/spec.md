## ADDED Requirements

### Requirement: Fernet-Backed Vault

All secret values (`Credential.encrypted_blob`, `LlmConfig.encrypted_api_key`) SHALL be encrypted at rest using `cryptography.fernet.Fernet`. A single process-wide `Fernet` instance SHALL be the only path used to encrypt or decrypt blobs.

#### Scenario: Encrypted bytes never include plaintext

- **WHEN** a `Credential` is persisted via `POST /api/credentials`
- **THEN** the `encrypted_blob` bytes SHALL be the output of `Fernet.encrypt(json.dumps(fields).encode())`, the plaintext SHALL NOT appear in any DB row, and the response body SHALL NOT include any plaintext value.

#### Scenario: Decryption is centralized

- **WHEN** the executor or LLM-config service needs a plaintext value
- **THEN** it SHALL call `crypto.decrypt(blob)` and SHALL NOT instantiate `Fernet` itself.

### Requirement: Master Key Bootstrap

The Fernet master key SHALL be resolved at startup in this order: (1) environment variable `AUTO_AGENT_SECRET_KEY`, (2) the file `backend/.secret_key`, (3) a freshly generated key written to `backend/.secret_key`.

#### Scenario: First boot generates the key file

- **WHEN** neither `AUTO_AGENT_SECRET_KEY` nor `backend/.secret_key` exists
- **THEN** the startup hook SHALL call `Fernet.generate_key()`, write the bytes to `backend/.secret_key`, and on POSIX systems set the file mode to `0600`; on Windows it SHALL log a warning that ACL-level protection is the user's responsibility.

#### Scenario: Env var overrides file

- **WHEN** `AUTO_AGENT_SECRET_KEY` is set and `backend/.secret_key` also exists
- **THEN** the env-var key SHALL be used and `backend/.secret_key` SHALL NOT be read.

#### Scenario: Key file is gitignored

- **WHEN** the repository is inspected
- **THEN** `.gitignore` (or `backend/.gitignore`) SHALL list `.secret_key` and `data/auto_agent.db`.

### Requirement: Masked API Responses

`GET` / `POST` / `PUT` responses for `Credential` and `LlmConfig` SHALL NEVER include plaintext secret material. They SHALL include a `masked_value` (credentials) or `api_key_masked` (LLM configs) field.

#### Scenario: Masked credential read

- **WHEN** the frontend calls `GET /api/credentials`
- **THEN** each item SHALL have shape `{id, name, kind, hint, masked_value, created_at, updated_at}` where `masked_value` is the literal string `"••••"` (or last-4 of the value if `hint == "show_last_4"`), and `encrypted_blob` SHALL NOT appear.

#### Scenario: Masked LLM config read

- **WHEN** the frontend calls `GET /api/llm-config`
- **THEN** each item SHALL have shape `{id, provider, model, base_url, api_key_masked, is_active, created_at, updated_at}` with `api_key_masked = "sk-…" + last_4(api_key)`.

### Requirement: Lookup-By-Name From Workflow Nodes

Workflow node `params` SHALL be allowed to contain interpolation tokens. The syntax is locked to **`{{cred.<credential_name>.<field>}}`** (whitespace tolerated inside the braces). Before the executor runs an action, a resolution pass SHALL walk the `params` tree — strings, lists, nested dicts — and replace every token with the decrypted field value.

#### Field name conventions

Field names inside a credential's encrypted blob are free-form strings, but the platform recommends these conventional names so workflows are predictable:

- `username`
- `password`
- `email`
- `api_key`
- `totp_secret`

Plus arbitrary user-defined keys for unusual cases. The interpolator is case-sensitive and SHALL NOT normalize field names.

#### Scenario: Login fill with credential reference

- **WHEN** a `fill` node has `params = {"selector":"#pwd", "value":"{{cred.bosch-login.password}}"}` and a `Credential` row exists with `name="bosch-login"` and a field `password="hunter2"`
- **THEN** the executor SHALL call `actions.fill("#pwd", "hunter2")` and SHALL NOT log the plaintext.

#### Scenario: Missing credential fails the node

- **WHEN** a token references a credential name that does not exist (or a field that does not exist on the credential)
- **THEN** the action SHALL raise a clear error, the executor SHALL emit `node_failed` with a non-leaking message (e.g. `unknown credential 'bosch-login'`), and the run SHALL stop.

### Requirement: Unresolved Tokens Fail Loudly

An unresolved `{{cred.<name>.<field>}}` token MUST fail the owning node loudly and SHALL be surfaced in the run log. The interpolator SHALL NOT silently substitute an empty string, SHALL NOT pass the literal token through to Playwright, and SHALL NOT continue to the next node.

#### Scenario: Token surfaces in run log

- **WHEN** a node has `params = {"value": "{{cred.unknown.password}}"}`
- **THEN** the executor SHALL emit a `node_failed` event whose `error` field reads e.g. `unknown credential 'unknown'` (or `credential 'bosch' has no field 'totp_secret'`), the event SHALL be persisted as a `RunEvent`, and no plaintext from any other credential SHALL appear in the message.

#### Scenario: Recursive interpolation refused

- **WHEN** a credential's decrypted field value itself contains a `{{cred.…}}` token
- **THEN** the interpolator SHALL NOT recurse; it SHALL substitute the value literally and SHALL NOT chase further tokens.

### Requirement: Update Replaces Encrypted Blob Atomically

A `PUT /api/credentials/{id}` request with a `fields` payload SHALL re-encrypt the full field map and replace `encrypted_blob` in a single transaction. Partial updates of individual fields SHALL be performed by merging plaintext server-side before re-encrypting.

#### Scenario: Partial field update

- **WHEN** the client PUTs `{fields: {"password": "new"}}` to a credential that already has `{"username":"u","password":"old"}`
- **THEN** the server SHALL decrypt the existing blob, merge `password = "new"`, re-encrypt the resulting `{"username":"u","password":"new"}`, and write it back; `updated_at` SHALL be refreshed.

### Requirement: Decryption Failure Surfaces Clearly

If decryption of a credential or LLM-config blob fails (corruption, key rotation without re-encryption, wrong env-var key), the API SHALL return HTTP 500 with a non-leaking message and SHALL log the underlying `InvalidToken`.

#### Scenario: Wrong key set

- **WHEN** `AUTO_AGENT_SECRET_KEY` is changed to a value different from the one used when blobs were written
- **THEN** any subsequent read of those rows SHALL return HTTP 500 with `{"detail":"credential vault: decryption failed; secret key may have changed"}` and SHALL NOT crash the process.

## API contract

| Method | Path | Request | Response | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/credentials` | — | `{items: CredentialMasked[]}` | list |
| `POST` | `/api/credentials` | `{name, kind, fields: dict<str,str>, hint?}` | `CredentialMasked` | encrypts on write |
| `GET` | `/api/credentials/{id}` | — | `CredentialMasked` | one |
| `PUT` | `/api/credentials/{id}` | `{name?, kind?, fields?: dict, hint?}` | `CredentialMasked` | partial; field merge before re-encrypt |
| `DELETE` | `/api/credentials/{id}` | — | `{ok:true}` | refuses (HTTP 409) if referenced by interpolation in any workflow's current version |

`CredentialMasked` shape:

```json
{
  "id": "cred_…",
  "name": "bosch-login",
  "kind": "login",
  "hint": null,
  "masked_value": "••••",
  "created_at": "2026-…",
  "updated_at": "2026-…"
}
```

## Data model

See `workflow-persistence` spec for the `Credential` table. This spec adds the resolution helper:

```python
# app/services/credentials.py
TOKEN_RE = re.compile(r"\{\{\s*cred\.(?P<name>[A-Za-z0-9_\-]+)\.(?P<field>[A-Za-z0-9_]+)\s*\}\}")

def resolve_params(params: dict, session: Session) -> dict:
    """Walk params, substitute every {{cred.name.field}} token with the
    decrypted field value. Raises ValueError on unknown name/field."""
```

## Out of Scope

- Per-credential ACLs / sharing.
- Hardware-backed key storage (TPM, OS keyring). Fernet on disk is acceptable for a single-user local platform.
- Automated key rotation. Future change can add `MultiFernet` with primary/secondary keys.
- Audit logging of credential reads.
