## 1. Backend data model

- [x] 1.1 Add `WorkflowCredential` SQLModel to `backend/app/db/models.py` (`workflow_id` FK + index, `credential_id` FK + index, `created_at`, `UniqueConstraint("workflow_id", "credential_id")`, auto-increment surrogate PK). Export from `__all__`.
- [x] 1.2 Create `backend/app/db/migrations.py` with `cleanup_credentials_on_first_run()`. Uses marker file `backend/.cleared_credentials`. Logs one `WARNING` line per outcome (cleared N rows / no rows present). Wipes `workflow_credential` first to respect the FK.
- [x] 1.3 Wire `cleanup_credentials_on_first_run()` into `app.main.lifespan` after `init_db()` and after `load_or_create_key()`. Keep `_seed_sample_if_empty()` after the cleanup.

## 2. Backend API

- [x] 2.1 Add `usage_count: int = 0` to `CredentialListItem` in `backend/app/schemas_api.py`. Add `WorkflowCredentialLinkRequest(_ApiModel)` with a single `credential_id: str`. Export from `__all__`.
- [x] 2.2 Update `backend/app/routers/credentials.py`:
  - import `WorkflowCredential` and `sqlalchemy.func`;
  - compute `usage_counts: dict[str, int]` once per `list_credentials` call;
  - pass the count into `_to_list_item`;
  - in `delete_credential`, hand-delete every `WorkflowCredential` row for that credential id before deleting the credential row (we don't have ON DELETE CASCADE enforced by SQLite).
- [x] 2.3 Add three endpoints to `backend/app/routers/workflows.py`:
  - `GET /api/workflows/{id}/credentials` → `list[CredentialListItem]` (rows for credentials linked to this workflow, with their own `usage_count`). 404 if workflow missing.
  - `POST /api/workflows/{id}/credentials` with `WorkflowCredentialLinkRequest` body → 200 + the linked `CredentialListItem`. 404 if workflow or credential missing, 409 if the link already exists.
  - `DELETE /api/workflows/{id}/credentials/{credential_id}` → 204. 404 if workflow or link missing.
- [x] 2.4 Update `workflow.updated_at` on both link and unlink so the workflow list sorts the most recently touched workflows to the top.

## 3. Backend interpolation

- [x] 3.1 Update `backend/app/services/credential_interpolation.py`:
  - `resolve_params(params, session, *, workflow_id: Optional[str] = None)`;
  - when `workflow_id` is supplied, load `set[str]` of allowed credential ids once via `WorkflowCredential` and check inside `_load_fields`;
  - on mismatch raise `CredentialResolutionError(f"credential 'X' is not linked to this workflow; open the workflow's '凭证' panel and add it before running")`;
  - keep the legacy "any credential by name" behaviour when `workflow_id is None`.
- [x] 3.2 Update `backend/app/executor.py::run_workflow` signature to accept `workflow_id: Optional[str] = None` and forward it into `resolve_params(...)`.
- [x] 3.3 Update `backend/app/services/runs.py::_drive_run` to capture `run.workflow_id` while the session is still open, then pass it into `run_workflow(...)`.

## 4. Frontend types and client

- [x] 4.1 Add `usage_count?: number` to `CredentialListItem` in `frontend/src/types-platform.ts`. Add `WorkflowCredentialLinkRequest` shape.
- [x] 4.2 Add three methods to `apiClient.workflows` in `frontend/src/api-platform.ts`:
  - `listCredentials(workflowId)` → `CredentialListItem[]`
  - `linkCredential(workflowId, credentialId)` → `CredentialListItem`
  - `unlinkCredential(workflowId, credentialId)` → `void`
- [x] 4.3 Extend the `WorkflowsApi` interface accordingly.

## 5. Frontend UI

- [x] 5.1 Author `frontend/src/pages/WorkflowCredentialsPanel.tsx`:
  - header "凭证" + count badge + "添加" button;
  - picker dropdown (in-panel disclosure, not a portal) excluding already-linked credentials;
  - linked-credential cards with name, optional description, masked-field chips (`{{cred.<name>.<field>}}` copy-on-click), and a "移除" button;
  - empty state: if there are no global credentials, link to `/credentials`; otherwise prompt to add one.
- [x] 5.2 Mount `<WorkflowCredentialsPanel workflowId={workflowId}/>` inside the right column of `WorkflowDetailPage`, between chat and run-log, in a `.workflow-detail-credentials` wrapper that caps height at 240 px and scrolls.
- [x] 5.3 Append the necessary CSS (`.workflow-detail-credentials`, `.workflow-credentials-*`, `.usage-badge`) to `frontend/src/shell/AppShell.css`.
- [x] 5.4 Update `frontend/src/pages/CredentialsListPage.tsx` to render a small `.usage-badge` next to each credential's name (zero state is muted; non-zero is highlighted) with a `title` tooltip showing the count.

## 6. OpenSpec

- [x] 6.1 Create `openspec/changes/per-workflow-credentials/` folder with `.openspec.yaml`, `proposal.md`, `design.md`, `tasks.md`.
- [x] 6.2 Author `specs/workflow-credential-link/spec.md` documenting the association entity, the three endpoints, the interpolation restriction, and the `usage_count` enrichment.

## 7. Verification

- [x] 7.1 `python -c "from app.db.models import WorkflowCredential; print('model ok')"` — must print ok.
- [x] 7.3 Backend pytest coverage in `backend/tests/test_workflow_credential_links.py` (link CRUD, usage_count, resolve_params enforcement). `scripts/credential_link_smoke.py` covers live HTTP smoke when backend is running.
- [ ] 7.4 `cd frontend && npm run build` succeeds with 0 errors.
- [ ] 7.5 Headless Playwright screenshot of the workflow detail page saved to `assets/per-workflow-credentials.png`, showing the new "凭证" panel and the "添加" button.
- [ ] 7.6 All spawned dev processes killed at the end.
