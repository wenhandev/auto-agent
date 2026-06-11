## ADDED Requirements

### Requirement: Workflow-Credential Association Table

The platform SHALL persist an explicit many-to-many association between workflows and credentials in a `workflow_credential` table. Each row SHALL store `(id, workflow_id, credential_id, created_at)`. The pair `(workflow_id, credential_id)` SHALL be unique. `workflow_id` SHALL be indexed. The table SHALL be created at startup by `SQLModel.metadata.create_all(engine)` alongside the rest of the schema; no separate migration tool is required.

#### Scenario: Table created on first boot

- **WHEN** the backend starts and `auto_agent.db` does not yet contain `workflow_credential`
- **THEN** the startup hook SHALL create the table and SHALL NOT crash on subsequent restarts when the table already exists.

#### Scenario: Duplicate pair refused at DB level

- **WHEN** a second row with the same `(workflow_id, credential_id)` pair is inserted
- **THEN** SQLite SHALL raise an integrity error and the API layer SHALL surface it as HTTP 409.

### Requirement: Sub-Resource Endpoints For Linking

The link SHALL be CRUD-managed through endpoints under `/api/workflows/{id}/credentials`. These endpoints SHALL live in the same router as the rest of workflow CRUD because the link is a sub-resource of a workflow.

#### Scenario: List linked credentials

- **WHEN** the client calls `GET /api/workflows/{id}/credentials`
- **THEN** the server SHALL return HTTP 200 with a JSON array of `CredentialListItem` objects, one per row in `workflow_credential` where `workflow_id == id`. Each item SHALL include `usage_count`. The array SHALL be ordered by credential name. Missing workflow SHALL return HTTP 404.

#### Scenario: Link a credential

- **WHEN** the client calls `POST /api/workflows/{id}/credentials` with body `{"credential_id": "<cid>"}`
- **THEN** the server SHALL insert a `workflow_credential` row, refresh `workflow.updated_at`, and SHALL return HTTP 200 with the linked credential's `CredentialListItem`. Missing workflow or missing credential SHALL return HTTP 404. A pre-existing link SHALL return HTTP 409 with `{"detail": "credential already linked to this workflow"}`.

#### Scenario: Unlink a credential

- **WHEN** the client calls `DELETE /api/workflows/{id}/credentials/{credential_id}`
- **THEN** the server SHALL delete the matching `workflow_credential` row, refresh `workflow.updated_at`, and SHALL return HTTP 204 with an empty body. Missing workflow or missing link row SHALL return HTTP 404.

### Requirement: Interpolation Restricted To Linked Credentials

When the executor runs a persisted `Run`, the credential interpolation pass SHALL receive the run's `workflow_id` and SHALL refuse to resolve any `{{cred.<name>.<field>}}` token whose credential is not linked to that workflow. The error SHALL be a `CredentialResolutionError` whose message contains the substring `"not linked"` and SHALL name the credential. The executor SHALL emit `node_failed` and `run_failed` events as it already does for any `CredentialResolutionError`.

#### Scenario: Linked credential resolves

- **WHEN** `Credential` `"a"` is linked to workflow `W` and node params contain `{{cred.a.username}}`
- **THEN** the interpolator SHALL substitute the decrypted `username` value and the executor SHALL proceed as normal.

#### Scenario: Unlinked credential fails loudly

- **WHEN** `Credential` `"a"` exists globally but is NOT linked to workflow `W` and node params contain `{{cred.a.username}}`
- **THEN** the interpolator SHALL raise `CredentialResolutionError("credential 'a' is not linked to this workflow; open the workflow's '凭证' panel and add it before running")`, the executor SHALL emit `node_failed` with that message verbatim, and SHALL NOT call the underlying action.

#### Scenario: Unknown credential still fails

- **WHEN** node params contain `{{cred.does_not_exist.x}}`
- **THEN** the interpolator SHALL raise `CredentialResolutionError("unknown credential 'does_not_exist'")` regardless of link state.

### Requirement: Legacy Ad-Hoc Runs Stay On Global Namespace

Runs initiated through the legacy `/ws/run` workflow-payload path (no `run_id`, ad-hoc workflow JSON) SHALL keep the pre-change behaviour: any credential by name resolves. The new restriction SHALL apply only when `workflow_id` is passed through the executor — i.e., only for persisted runs created via `POST /api/workflows/{id}/runs`.

#### Scenario: Ad-hoc run resolves any credential

- **WHEN** the executor is invoked with `session=…` but `workflow_id=None`
- **THEN** `resolve_params` SHALL behave as before this change (lookup-by-name against the full `credential` table).

### Requirement: Usage Count Surfaced In Credential List

`GET /api/credentials` SHALL include a `usage_count: int` field on every `CredentialListItem`, equal to the number of `workflow_credential` rows with that `credential_id`. The frontend `CredentialsListPage` SHALL render a small badge next to each credential's name showing the count.

#### Scenario: Zero usage

- **WHEN** a freshly created credential has no link rows
- **THEN** the list response item SHALL have `"usage_count": 0` and the badge SHALL render as `0` with a muted style.

#### Scenario: Non-zero usage

- **WHEN** a credential is linked to two workflows
- **THEN** the list response item SHALL have `"usage_count": 2` and the badge SHALL render with a highlighted style.

### Requirement: Credential Delete Cascades Through Links

`DELETE /api/credentials/{id}` SHALL remove every `workflow_credential` row referencing the credential before deleting the credential row, in a single transaction. SQLite is not configured to enforce ON DELETE CASCADE, so the cascade SHALL be performed in application code.

#### Scenario: Delete a linked credential

- **WHEN** credential `"a"` is linked to two workflows and the client calls `DELETE /api/credentials/{a_id}`
- **THEN** the two link rows SHALL be removed first, then the credential row, the response SHALL be HTTP 200 with `{"ok": true}`, and a subsequent `GET /api/credentials` SHALL not list `"a"`.

### Requirement: One-Time Credential Cleanup On First Boot

On first boot after this change ships, the backend SHALL DELETE every existing row in `credential` (operator-requested clean reset) and SHALL write a sibling marker file `backend/.cleared_credentials` so subsequent boots SHALL NOT repeat the wipe. The migration SHALL log one `WARNING` line describing the outcome (row count cleared, or "no rows present"). The marker file path SHALL be matched by the gitignore patterns already covering `.secret_key*`.

#### Scenario: First boot with existing rows

- **WHEN** the backend starts and `backend/.cleared_credentials` does not exist and the `credential` table has N > 0 rows
- **THEN** the helper SHALL delete every `workflow_credential` row, delete every `credential` row, write the marker file, and log `"credential cleanup migration: removed N existing credential row(s); operator requested a clean reset after introducing per-workflow scoping"`.

#### Scenario: First boot with empty table

- **WHEN** the backend starts and `backend/.cleared_credentials` does not exist and the `credential` table is empty
- **THEN** the helper SHALL write the marker file and log `"credential cleanup migration: no rows present; marker written"` and SHALL NOT issue a DELETE.

#### Scenario: Subsequent boots are no-ops

- **WHEN** the backend starts and `backend/.cleared_credentials` already exists
- **THEN** the helper SHALL return immediately and SHALL NOT touch the `credential` table.

## API contract

| Method | Path | Request | Response | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/workflows/{id}/credentials` | — | `CredentialListItem[]` | linked credentials for this workflow, ordered by name |
| `POST` | `/api/workflows/{id}/credentials` | `{credential_id: str}` | `CredentialListItem` | link; 409 if duplicate, 404 if missing |
| `DELETE` | `/api/workflows/{id}/credentials/{credential_id}` | — | 204 | unlink; 404 if missing |

`CredentialListItem` shape (full, after this change):

```json
{
  "id": "cred_…",
  "name": "bosch-login",
  "description": "...",
  "field_names": ["username", "password"],
  "updated_at": "2026-…",
  "usage_count": 1
}
```

## Data model

```python
class WorkflowCredential(SQLModel, table=True):
    __tablename__ = "workflow_credential"
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True, nullable=False)
    credential_id: str = Field(foreign_key="credential.id", index=True, nullable=False)
    created_at: datetime
    __table_args__ = (
        UniqueConstraint("workflow_id", "credential_id", name="uq_workflow_credential_pair"),
    )
```

## Interpolation signature

```python
def resolve_params(
    params: dict[str, Any],
    session: Session,
    *,
    workflow_id: Optional[str] = None,
) -> dict[str, Any]:
    """Walk params, substitute every {{cred.name.field}} token with the
    decrypted field value. If workflow_id is supplied, only credentials
    linked to that workflow may resolve; any other token raises
    CredentialResolutionError."""
```

## Out of Scope

- Per-credential field-level ACLs (e.g. "may read password but not totp_secret").
- A run-preflight modal that scans the workflow JSON for `{{cred.…}}` tokens before `POST /api/runs` and warns about unlinked ones. The runtime error is the source of truth for now.
- Auto-linking heuristics ("the workflow mentions `{{cred.bosch-login.password}}` — link it for the operator").
- Per-`WorkflowVersion` scoping. The link belongs to the `Workflow`.
- Refusing `DELETE /api/credentials/{id}` when `usage_count > 0`. The badge already signals usage and the link rows are cheap to recreate.
