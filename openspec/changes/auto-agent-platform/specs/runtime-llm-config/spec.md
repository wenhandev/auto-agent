## ADDED Requirements

### Requirement: DB-Backed LLM Settings

LLM provider, model, API key, and base URL SHALL be storable as `LlmConfig` rows in the DB. The API key bytes SHALL be encrypted with the same Fernet key used by the credential vault.

#### Scenario: Create stores encrypted key

- **WHEN** the client POSTs `/api/llm-config {provider:"openai", model:"gpt-4o", api_key:"sk-…", base_url:"https://relay/…"}`
- **THEN** a new `LlmConfig` row SHALL be inserted with `encrypted_api_key = Fernet.encrypt("sk-…")`, `is_active=false` by default, and the response SHALL include `api_key_masked` but SHALL NOT include the plaintext or the encrypted bytes.

#### Scenario: Update is partial

- **WHEN** the client PUTs `/api/llm-config/{id} {model: "gpt-4o-mini"}` (no `api_key` field)
- **THEN** the existing encrypted key SHALL be left untouched and only `model` SHALL be updated.

#### Scenario: Update with new api_key re-encrypts

- **WHEN** the client PUTs `/api/llm-config/{id} {api_key: "sk-new"}`
- **THEN** the row's `encrypted_api_key` SHALL be replaced with `Fernet.encrypt("sk-new")` and `updated_at` SHALL be refreshed.

### Requirement: Exactly One Active Config

At most one `LlmConfig` row SHALL be `is_active=True` at any given moment. Historical inactive rows MAY be retained indefinitely; the platform does not auto-delete deactivated configs. Activating a row SHALL deactivate any previously active row in the same transaction. The active row is used by **all** agents (planner, editor, fuzzy, extractor); there are no per-purpose model fields.

#### Scenario: Activation atomically swaps

- **WHEN** `POST /api/llm-config/{B}/activate` is called and row `A` was previously active
- **THEN** in a single DB transaction `A.is_active` SHALL become `False` and `B.is_active` SHALL become `True`; a subsequent failure SHALL roll both back.

#### Scenario: Already-active is idempotent

- **WHEN** `POST /api/llm-config/{A}/activate` is called and `A` is already active
- **THEN** the call SHALL succeed with HTTP 200 and SHALL NOT churn `updated_at`.

### Requirement: Settings Precedence (All-Or-Nothing)

The platform SHALL compute the **effective** LLM settings on each call to `get_adk_model_cached()`. Precedence is **all-or-nothing**:

1. If a row with `is_active=True` exists AND every required field is present (`provider`, `model`, `api_key_ciphertext`), that row SHALL be used in full. `base_url` is optional.
2. Otherwise (no active row, or active row missing any required field), `.env` SHALL be used in full as the fallback.

Per-field merging between the DB row and `.env` is forbidden. When an active row is refused due to missing required fields, the platform SHALL log a warning at startup naming the row id and the missing field(s).

#### Scenario: DB row wins when complete

- **WHEN** an active `LlmConfig` row has all of `provider="openai"`, `model="gpt-4o"`, `api_key_ciphertext` non-empty and `.env` has `LLM_PROVIDER=google`
- **THEN** the effective provider SHALL be `openai` (from the DB row) and `.env` SHALL be ignored.

#### Scenario: Fallback to .env

- **WHEN** no `LlmConfig` row is active and `.env` is configured for OpenAI
- **THEN** the effective provider SHALL be `openai` from `.env`, and `get_adk_model_cached()` SHALL work without any DB row.

#### Scenario: Refuse partial DB row, fall back fully to .env

- **WHEN** an active `LlmConfig` row has `provider="openai"` and `model="gpt-4o"` but `api_key_ciphertext` is empty AND `.env` has a complete OpenAI configuration
- **THEN** the platform SHALL refuse the DB row entirely, log a warning identifying the missing `api_key` field, and use `.env` as the complete fallback (provider, model, api_key, base_url all from `.env`); per-field merging SHALL NOT occur.

#### Scenario: Both partial DB row and partial .env fail loudly

- **WHEN** the active DB row is missing `api_key_ciphertext` AND `.env` is also missing a usable provider key
- **THEN** `effective_settings()` SHALL raise a clear `MissingApiKeyError` naming both the refused DB row and the missing env vars so the user can fix one or the other.

### Requirement: Model Cache Hot Reload

`get_adk_model_cached()` SHALL memoize the ADK model object keyed by a fingerprint of the effective settings. Whenever an `LlmConfig` row that is (or becomes) active is created, updated, activated, or deleted, the cache SHALL be invalidated.

#### Scenario: Cache hit on repeat call

- **WHEN** `get_adk_model_cached()` is called twice in a row with no changes to active config
- **THEN** the second call SHALL return the same object (cache hit) and SHALL NOT instantiate ADK / LiteLLM again.

#### Scenario: Activation invalidates cache

- **WHEN** `POST /api/llm-config/{id}/activate` succeeds
- **THEN** the cache SHALL be cleared and the next call to `get_adk_model_cached()` SHALL build a fresh model from the newly active row.

#### Scenario: Editing active row invalidates cache

- **WHEN** `PUT /api/llm-config/{id}` updates an `LlmConfig` row whose `is_active=True`
- **THEN** the cache SHALL be cleared after the DB commit.

### Requirement: Effective Settings Endpoint

`GET /api/llm-config/effective` SHALL return a masked snapshot of what `get_adk_model_cached()` will use next, including whether the source is an `LlmConfig` row or the `.env` fallback.

#### Scenario: DB row reported

- **WHEN** a row is active
- **THEN** the response SHALL be `{source: "db", id: "lc_…", provider, model, base_url, api_key_masked}`.

#### Scenario: Env fallback reported

- **WHEN** no row is active
- **THEN** the response SHALL be `{source: "env", provider, model, base_url, api_key_masked}`.

### Requirement: Delete Guardrails

`DELETE /api/llm-config/{id}` SHALL succeed for inactive rows. For the active row it SHALL succeed only if the `.env` fallback would yield a complete configuration; otherwise SHALL return HTTP 409 explaining that the deletion would leave the platform with no usable LLM.

#### Scenario: Safe delete of inactive

- **WHEN** an inactive `LlmConfig` row is deleted
- **THEN** the row SHALL be removed and the cache SHALL NOT need invalidating.

#### Scenario: Refuse last-resort delete

- **WHEN** the only active `LlmConfig` row is deleted AND `.env` has no `LLM_PROVIDER`/keys set
- **THEN** the API SHALL return HTTP 409 with a clear message and the row SHALL be retained.

#### Scenario: Delete active falls back to env

- **WHEN** the active row is deleted AND `.env` has a complete config
- **THEN** the row SHALL be removed, the cache SHALL be invalidated, and the next call SHALL use `.env`.

### Requirement: Settings UI

The frontend SHALL include a `/settings` page that lists all `LlmConfig` rows (masked), allows create / edit / delete / activate, and shows which row (or `.env`) is currently in use. The page SHALL NOT require a backend restart for any change to take effect.

#### Scenario: Activate from UI

- **WHEN** the user clicks "Activate" on a row in the settings page
- **THEN** the page SHALL POST to `/api/llm-config/{id}/activate`, re-fetch `/api/llm-config/effective`, and display the new active row without a reload.

## API contract

| Method | Path | Request | Response | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/llm-config` | — | `{items: LlmConfigMasked[]}` | list |
| `POST` | `/api/llm-config` | `{provider, model, api_key, base_url?, extra?}` | `LlmConfigMasked` | create (inactive by default) |
| `PUT` | `/api/llm-config/{id}` | partial | `LlmConfigMasked` | update; invalidates cache if active |
| `DELETE` | `/api/llm-config/{id}` | — | `{ok:true}` | guarded |
| `POST` | `/api/llm-config/{id}/activate` | — | `LlmConfigMasked` | sets `is_active`, clears others, invalidates cache |
| `GET` | `/api/llm-config/effective` | — | `EffectiveLlmSettingsMasked` | source = "db" \| "env" |

`LlmConfigMasked`:

```json
{
  "id": "lc_…",
  "provider": "openai",
  "model": "gpt-4o",
  "base_url": "https://relay.example.com",
  "api_key_masked": "sk-…AbCd",
  "is_active": true,
  "extra": null,
  "created_at": "2026-…",
  "updated_at": "2026-…"
}
```

## Data model

See `workflow-persistence` for the `LlmConfig` table.

```python
# app/services/llm_settings.py
@dataclass(frozen=True)
class EffectiveLlmSettings:
    source: Literal["db", "env"]
    id: str | None
    provider: Literal["openai", "google"]
    model: str
    api_key: str
    base_url: str | None
    extra: dict | None

def effective_settings(session: Session) -> EffectiveLlmSettings: ...
def get_adk_model_cached() -> Any: ...   # lru_cache(maxsize=1) keyed by fingerprint
def invalidate_model_cache() -> None: ...
```

## Required DB fields

`LlmConfig` rows have these required fields (any of them missing causes the row to be refused under all-or-nothing precedence):

- `provider`
- `model`
- `api_key_ciphertext` (Fernet-encrypted bytes)

Optional fields:

- `base_url`
- `extra` / extra params (provider-specific)

## Out of Scope

- Per-purpose configs (separate planner / fuzzy / editor / extractor models). One active row applies to all agents — this is locked.
- Provider-level rate limit / quota tracking.
- Streaming model output (still not supported in this iteration).
- Anthropic / local-model support. Provider stays `{openai, google}`.
