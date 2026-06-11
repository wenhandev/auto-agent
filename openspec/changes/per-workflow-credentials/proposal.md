## Why

The `auto-agent-platform` change introduced a **global** credential vault. Any workflow can interpolate `{{cred.<name>.<field>}}` and the executor resolves it against the only namespace the platform has — the full `credential` table. That is fine for a single-user POC but it is the wrong default the moment a second workflow exists:

1. A workflow author who only ever needs the `bosch-login` credential nonetheless gets resolution against every credential, including secrets that belong to unrelated automations (Jira API key, internal LLM relay token, etc.). One typo in a token name turns into "wrong workflow accidentally fills in someone else's token".
2. There is no UI signal of *which* credentials a given workflow actually depends on. The credential page lists everything; the workflow page mentions nothing. Reviewing a workflow before running it means re-reading the whole node graph and grepping for `{{cred.…}}` by eye.
3. Future multi-user work (the reserved `owner_id` column) needs per-workflow scoping to be the *enforcement* point — otherwise we'd have to retrofit it at the same time we add auth, which compounds risk.

This change scopes credential interpolation to an explicit **per-workflow allowlist**. Credentials stay global (still one Fernet vault, still global uniqueness on `name`), but each workflow declares which subset it can use. The executor enforces the allowlist when resolving tokens; tokens that reference a credential not on the list fail loudly at run time with an actionable error.

## What Changes

- **Data model**: add a `WorkflowCredential` association table (many-to-many between `Workflow` and `Credential`), unique on the `(workflow_id, credential_id)` pair, indexed by `workflow_id`. Created by `SQLModel.metadata.create_all(engine)` at startup — no Alembic.
- **Backend API**: add three sub-resource endpoints on `/api/workflows/{id}/credentials` — list / link / unlink. Re-use the existing `CredentialListItem` shape for both the "linked credentials of a workflow" response and the credentials page list, and add a single new field `usage_count: int` (how many workflows link this credential) so the credentials page can show a small badge.
- **Interpolation restriction**: `credential_interpolation.resolve_params` gains a keyword-only `workflow_id` parameter. When supplied, only credentials linked to that workflow may resolve; any other token raises `CredentialResolutionError("credential 'X' is not linked to this workflow")`. The executor and `services.runs` pass the run's `workflow_id` through. Ephemeral runs that never persisted a `Run` (the `/ws/run` workflow-payload path) keep the legacy behaviour — `workflow_id` defaults to `None` so they can resolve any global credential — because they have no link table row to consult.
- **Frontend**: add a "凭证" panel on the workflow detail page (third panel under the chat) listing linked credentials with name + masked field tokens + "添加" / "移除" buttons; the picker excludes already-linked credentials. The credentials page gains a small usage badge next to each name.
- **Data cleanup**: on first boot after this change, run an idempotent migration helper that DELETEs every existing row in `credential` (operator-requested clean reset). Marker file `backend/.cleared_credentials` prevents re-runs.

## Capabilities

### New Capabilities

- `workflow-credential-link`: the association entity, the three sub-resource endpoints (`GET/POST/DELETE /api/workflows/{id}/credentials`), the `usage_count` enrichment on `CredentialListItem`, and the run-time enforcement that a token may only resolve against a linked credential.

### Modified Capabilities

- `credential-vault` (from `auto-agent-platform`): the interpolation contract changes from "any credential by name" to "any credential by name that is linked to this run's workflow". Unresolved-token semantics (`node_failed` event, no plaintext leak) are unchanged.

## Impact

- **Backend**: new `WorkflowCredential` table, three new endpoints, one new keyword argument on `resolve_params`, one new keyword argument on `run_workflow`, one extra `select` per credential listed (acceptable at POC scale; can be replaced with a single `JOIN … GROUP BY` later). New `backend/app/db/migrations.py` for the one-time wipe; sibling marker file `backend/.cleared_credentials` is gitignored along the same pattern as `auto_agent.db`.
- **Frontend**: new `WorkflowCredentialsPanel.tsx` mounted from `WorkflowDetailPage`; one extra row in `CredentialsListPage` showing the usage badge; three new methods on `apiClient.workflows`. No edits under `frontend/src/chat/` or `frontend/src/components/`.
- **Runtime**: existing seeded `示例工作流` becomes "no linked credentials" after the cleanup, which is the desired empty-state for the new UI. Workflows that did not use credential interpolation are unaffected. Workflows that *did* will fail at the affected node with the new "not linked to this workflow" message; the fix is one click ("添加" in the new panel).
- **Out of scope**: per-credential ACLs across users (waiting for `owner_id`); a UI preflight modal that catches unlinked tokens before `POST /api/runs` (the runtime error is sufficient and actionable for now); auto-linking heuristics that scan node `params` for `{{cred.…}}` tokens.
