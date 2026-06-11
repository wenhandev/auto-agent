## Context

The credential vault from `auto-agent-platform` is global: a single `credential` table, encrypted with Fernet, looked up by `name`. `services.credential_interpolation.resolve_params(params, session)` walks node params and substitutes `{{cred.<name>.<field>}}` tokens against that global namespace. The executor calls it once per node before running the action.

That is the wrong default for a system that already has multiple workflows. Two concrete failure modes:

1. **Token namespace collision in the user's head**: a workflow author renames `bosch-login` → `bosch-corp` in the credentials page; another workflow that still uses the old name silently breaks at runtime ("unknown credential 'bosch-login'") even though the secret physically exists under the new name. The author has no UI cue that workflow A *was* depending on it.
2. **Blast radius on a typo**: a workflow whose business purpose is "extract prices from `shop.example.com`" should not be able to fill in the platform's internal LLM relay token just because the author typed `{{cred.llm-relay.api_key}}` somewhere. Today nothing in the system says "this workflow has no business touching that credential".

We want both: keep the vault global (one Fernet key, one place to manage secrets), but require workflows to *opt into* the credentials they use. The opt-in is the enforcement point.

## Goals / Non-Goals

**Goals**

- A workflow declares which credentials it can use through an explicit, persisted link.
- The executor refuses to resolve a token whose credential is not on the declared list, with an error message that points the operator straight to the fix.
- The link is round-trippable through three HTTP endpoints (list / link / unlink) and surfaced inline on the workflow detail page.
- The credentials page shows usage so an operator can see "this credential is used by N workflows" before deleting it.

**Non-Goals**

- Field-level or scoped tokens (e.g. "this workflow may read `password` but not `totp_secret`"). The unit of authorisation is the whole credential.
- Auto-detection of `{{cred.…}}` tokens at save time. The author still has to click "添加" in the panel. A future preflight modal could parse the workflow JSON and warn before the run starts.
- Per-version scoping. The link belongs to the `Workflow`, not the `WorkflowVersion`. Editing a workflow does not invalidate its credential links. This matches the way the existing `ChatSession` is per-`Workflow`, not per-version.
- Concurrency on the link table. Single-user POC, no row-level contention.

## Decisions

### Decision 1: Many-to-many association table over JSON column on `Workflow`

We considered storing the link list as a JSON column on `Workflow` (e.g. `linked_credential_ids: list[str]`). The MTM table is better:

- It keeps the foreign-key invariant: deleting a `Credential` cascades through the link table cleanly (we do it manually in `delete_credential` but the FK is still the source of truth in the model).
- It supports the reverse query "which workflows use this credential?" — needed for the `usage_count` badge — with one GROUP BY, no JSON parsing.
- It generalises to a future multi-user `owner_id` column on the link itself ("workflow A linked credential B *as user U*") without re-shaping a JSON blob.

Schema:

```python
class WorkflowCredential(SQLModel, table=True):
    __tablename__ = "workflow_credential"
    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: str = Field(foreign_key="workflow.id", index=True)
    credential_id: str = Field(foreign_key="credential.id", index=True)
    created_at: datetime
    __table_args__ = (UniqueConstraint("workflow_id", "credential_id"),)
```

Auto-increment surrogate PK (rather than composite `(workflow_id, credential_id)`) because it makes the link easy to surface as a stable ID in future audit log entries if we ever want them, with no downside for query patterns we care about.

### Decision 2: Optional `workflow_id` in `resolve_params`, not a separate function

`resolve_params(params, session, *, workflow_id=None)` is backward compatible: every caller that hasn't been migrated keeps working. The executor's call site is updated; the ephemeral `/ws/run` path that streams a workflow payload without persisting it stays on the legacy global-namespace path because there *is* no workflow id to consult. That path is opt-in for power users running ad-hoc Workflow JSON; if and when we want to lock it down we can require either a stored workflow or no credentials at all.

The enforcement check sits inside `_load_fields`, which is reached only when a token is actually present. Workflows with no credential tokens at all pay zero new cost.

### Decision 3: 409 on duplicate link, 204 on unlink

Both shapes match the rest of the API. `POST` on an already-linked pair returns 409 with `{"detail": "credential already linked to this workflow"}` instead of silently no-op'ing — the frontend's button is hidden when the credential is already in the linked list, so a 409 here means a stale client; we want to surface it.

`DELETE` returns 204 (empty body) per FastAPI/REST convention. The frontend invalidates the linked-list query on success and the row disappears.

### Decision 4: `usage_count` returned by `CredentialListItem` instead of a separate endpoint

The credentials page already calls `apiClient.credentials.list()` on mount. Adding a second round-trip just for the badge is wasteful at the POC's scale (single-digit credentials). We compute the counts with one extra `SELECT credential_id, COUNT(*) FROM workflow_credential GROUP BY credential_id` per `list_credentials` call and join in Python. If row counts ever grow this becomes a real JOIN.

### Decision 5: One-time wipe via marker file

The operator asked for a clean reset of existing credential rows. We could:

- **(rejected)** drop the table on every boot — destroys freshly created credentials on every restart.
- **(rejected)** read an env var — operator has to remember to unset it.
- **(chosen)** drop once, then write `backend/.cleared_credentials` as a marker; subsequent boots see the marker and skip. Idempotent, doesn't require the operator to do anything after the first boot, doesn't ship a destructive default. The marker file is gitignored under the same pattern as the database.

The migration logs one `WARNING` line with the row count so the operator can confirm it ran. If the table is already empty on first boot, we still write the marker (with `"no rows to clear\n"`) so the second boot is symmetric — i.e., the migration is always single-fire.

### Decision 6: Panel placement on the workflow detail page

The header is already crowded (name, status pill, version selector, "凭证" link, Run, Abort). Adding a counted pill there is feasible but trades visibility for density. We add the panel as the **third column row** in the right-hand stack (chat | credentials | run-log), capped at 240 px. That keeps the panel always visible, always near the action it informs, and lets the user expand the picker without leaving the page. The header link to the global credentials page is unchanged.

### Decision 7: Ephemeral workflow runs keep the legacy global resolver

The `/ws/run` endpoint accepts both `run_id` (persisted run) and `workflow` (ad-hoc payload). The latter has no `workflow_id` to consult — it isn't persisted. We default `workflow_id=None` in `resolve_params` and in `run_workflow`, which preserves today's "any credential by name" behaviour for ad-hoc runs. The persisted run path (`POST /api/runs` → scheduler → `_drive_run`) is what enforces the link. This is a deliberate compromise: ad-hoc runs are a developer affordance, not a production code path; locking them down would break the smoke scripts that drive the executor directly.

## Risks / Trade-offs

- **A workflow that previously ran clean will now fail at the first credential token after this change**, until the operator adds the link. This is intentional ("loud failure" is the security stance) and the error message tells the operator exactly what to do. The seeded `示例工作流` has no credential tokens, so it remains green.
- **`usage_count` is computed on every credential-list call.** O(credentials × 1) extra query plus one aggregate query. Acceptable; can be a single JOIN later.
- **No cascade delete on the FK.** SQLite respects FKs only when `PRAGMA foreign_keys = ON`, which the engine doesn't currently set. We compensate by explicitly deleting link rows in `delete_credential`. A future change can flip the PRAGMA at engine create and drop the manual delete.

## Migration Plan

1. Drop new model + migrations + endpoints; `init_db()` already runs at startup and `create_all` will pick up the new table.
2. First boot after deploy: the cleanup migration removes any rows in `credential` (operator asked for a clean reset) and writes `backend/.cleared_credentials`. Logged with a single `WARNING` line.
3. Operator (re)creates credentials through the UI.
4. For each workflow that needs a credential, the operator clicks "添加" in the new panel.
5. Re-runs now succeed; tokens that reference unlinked credentials produce a clear `node_failed` event and the operator can fix it from the same page.

## Open Questions

- Should the UI also offer a "scan workflow for `{{cred.…}}` tokens" button that pre-fills the picker with the credentials a workflow appears to use? Out of scope for this change, easy follow-up.
- Should `DELETE /api/credentials/{id}` refuse with HTTP 409 when `usage_count > 0`? Today it removes the link rows and deletes the credential. We considered refusing, but the badge already signals usage and the link rows are cheap to recreate; deferring to a later "soft delete" / archive flow.
