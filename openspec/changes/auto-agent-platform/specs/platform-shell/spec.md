## ADDED Requirements

### Requirement: Sidebar Navigation Layout

The frontend SHALL render a persistent sidebar on the left containing exactly four primary navigation entries: `Workflows`, `Credentials`, `Run history`, `Settings`. The main content area on the right SHALL render the active route via `react-router-dom`'s `<Outlet/>`.

#### Scenario: Sidebar always visible

- **WHEN** any page is rendered (workflows list, workflow detail, credentials, runs, settings)
- **THEN** the sidebar SHALL be visible on the left with the active entry highlighted; clicking another entry SHALL navigate without a full page reload.

#### Scenario: Logo or app title

- **WHEN** the sidebar is rendered
- **THEN** the top of the sidebar SHALL contain a short app title link ("auto-agent" or the existing brand) that navigates to `/workflows`.

### Requirement: Routing Map

`react-router-dom` v6 SHALL define exactly these routes inside the shell:

| Path | Page | Notes |
| --- | --- | --- |
| `/` | redirect to `/workflows` | |
| `/workflows` | Workflows list | |
| `/workflows/new` | Workflows list with "Create" modal open OR redirect to a freshly created blank workflow | choose one and document |
| `/workflows/:id` | Workflow detail (canvas + chat + run log) | |
| `/credentials` | Credentials list + create/edit modal | |
| `/runs` | Runs list (filterable by workflow) | |
| `/runs/:id` | Run replay page | |
| `/settings` | LLM config CRUD | |
| `*` | 404 fallback inside the shell | |

#### Scenario: Default route

- **WHEN** the user opens `/`
- **THEN** the router SHALL redirect to `/workflows`.

#### Scenario: 404 stays inside shell

- **WHEN** the user navigates to a path not in the map
- **THEN** a "page not found" message SHALL render in the content area with the sidebar still visible.

### Requirement: Workflows List Page

`/workflows` SHALL fetch `GET /api/workflows` on mount and render the list with name, last-updated, and last-run status. Each row SHALL link to `/workflows/:id`. A "New workflow" button SHALL be available; it MAY open a modal that accepts either a free-text description (calls `POST /api/workflow/generate`) or a name-only blank workflow (`POST /api/workflows`).

#### Scenario: Empty state

- **WHEN** there are zero workflows
- **THEN** the page SHALL display an empty-state with a prominent "Generate from description" / "Create blank" choice.

### Requirement: Workflow Detail Page Layout

`/workflows/:id` SHALL fetch `GET /api/workflows/{id}` on mount and render a three-pane layout:

- Left pane: the existing `WorkflowCanvas` driven by the workflow JSON.
- Top-right pane: chat panel (mounted from `chat-authoring`).
- Bottom-right pane: run log + "Run Now" button.

Workflow rename (in-place) SHALL be available in the header of the page.

#### Scenario: Three-pane structure

- **WHEN** the user opens `/workflows/:id`
- **THEN** the page SHALL render all three panes simultaneously and the canvas SHALL show the current `WorkflowVersion.workflow_json`.

#### Scenario: New version replaces canvas

- **WHEN** a chat turn produces a new `WorkflowVersion`
- **THEN** the canvas SHALL update to the new JSON within one render cycle, the run log SHALL NOT be cleared, and the chat panel SHALL append the assistant message.

### Requirement: Credentials Page

`/credentials` SHALL list credentials returned by `GET /api/credentials` (masked) and SHALL allow create / edit / delete via modals that POST plaintext field maps to the backend. Plaintext values SHALL NEVER be rendered after the modal closes; subsequent reads display `••••`.

#### Scenario: Add credential modal

- **WHEN** the user clicks "Add credential" and submits `{name:"x", kind:"login", fields:{username:"u", password:"p"}}`
- **THEN** the frontend SHALL POST to `/api/credentials`, append the masked result to the list, and clear the modal state.

#### Scenario: No plaintext leakage on edit

- **WHEN** the user clicks "Edit" on an existing credential
- **THEN** the edit modal SHALL show the `name`, `kind`, `hint`, and a placeholder for each field (e.g. `Leave empty to keep current`) and SHALL NOT pre-fill any plaintext.

### Requirement: Runs Page And Replay Page

`/runs` SHALL list recent runs (filterable by `workflow_id` via a query param). Clicking a row navigates to `/runs/:id` which renders the replay player from the `run-history` spec.

#### Scenario: Filter by workflow

- **WHEN** the user clicks "View runs" from a workflow detail page
- **THEN** the frontend SHALL navigate to `/runs?workflow_id=wf_…` and the runs page SHALL pre-apply that filter.

### Requirement: Settings Page

`/settings` SHALL render the LLM-config CRUD UI described in `runtime-llm-config`. A "Currently in use" banner at the top SHALL show the active row (or `.env` fallback) based on `GET /api/llm-config/effective`.

#### Scenario: Banner reflects current state

- **WHEN** the settings page mounts
- **THEN** it SHALL call `GET /api/llm-config/effective` and render a single-line banner showing the source ("DB row" vs "fallback to .env"), provider, model, and masked api key.

### Requirement: Style And Theming Parity

The platform shell SHALL keep visual continuity with the MVP: dark theme, monospaced labels on nodes, the existing `GlowNode` styling SHALL NOT be modified. Sidebar styling SHALL be consistent with the existing CSS variables used in `App.css` / `GlowNode.css`.

#### Scenario: GlowNode unchanged

- **WHEN** the platform is rendered
- **THEN** the `GlowNode` component SHALL behave identically to the MVP for `idle | running | success | error` states.

### Requirement: Sidebar Does Not Touch Canvas Internals

The platform-shell sibling SHALL NOT modify `WorkflowCanvas`, `GlowNode`, `RunLog`, `NodeInspector`, `ResultPanel`, or `store.ts` beyond what is strictly required to host them inside a routed page (typically: an `id`-from-URL `useEffect` that calls `setWorkflow(...)`).

#### Scenario: Canvas code untouched

- **WHEN** the platform shell is implemented
- **THEN** a diff against the MVP frontend SHALL show no functional changes to `WorkflowCanvas.tsx`, `GlowNode.tsx`, `GlowNode.css`, `RunLog.tsx`, `RunLog.css`, `NodeInspector.tsx`, `ResultPanel.tsx`, or `ws.ts`.

## API contract

The platform-shell does not introduce new HTTP endpoints. It consumes:

- `GET /api/workflows`, `GET /api/workflows/{id}`, `POST /api/workflows`, `PUT /api/workflows/{id}`, `DELETE /api/workflows/{id}` (from `workflow-persistence`).
- `GET /api/credentials`, `POST /api/credentials`, `PUT /api/credentials/{id}`, `DELETE /api/credentials/{id}` (from `credential-vault`).
- `GET /api/runs`, `GET /api/runs/{id}`, `POST /api/runs` (from `run-history`).
- `GET /api/llm-config`, `POST /api/llm-config`, `PUT /api/llm-config/{id}`, `DELETE /api/llm-config/{id}`, `POST /api/llm-config/{id}/activate`, `GET /api/llm-config/effective` (from `runtime-llm-config`).
- `GET /api/chat/{session_id}`, `POST /api/chat/{session_id}/messages` (from `chat-authoring`).
- `WS /ws/run` (from `run-history` / MVP).

## Data model

None added by this spec. The shell is presentation only.

```text
frontend/src/
├── main.tsx                      # mounts <RouterProvider/>
├── routes.tsx                    # route map
├── shell/
│   ├── Shell.tsx                 # sidebar + Outlet
│   ├── Sidebar.tsx
│   └── Shell.css
├── pages/
│   ├── WorkflowsListPage.tsx
│   ├── WorkflowDetailPage.tsx    # mounts existing canvas + new chat panel + run log
│   ├── CredentialsPage.tsx
│   ├── RunsListPage.tsx
│   ├── RunReplayPage.tsx
│   ├── SettingsPage.tsx
│   └── NotFoundPage.tsx
├── components/                   # MVP files unchanged
│   ├── GlowNode.tsx              (unchanged)
│   ├── GlowNode.css              (unchanged)
│   ├── WorkflowCanvas.tsx        (unchanged)
│   ├── RunLog.tsx                (unchanged)
│   ├── RunLog.css                (unchanged)
│   ├── NodeInspector.tsx         (unchanged)
│   ├── ResultPanel.tsx           (unchanged)
│   ├── NLInput.tsx               (used inside WorkflowsListPage's create modal)
│   └── NLInput.css               (unchanged)
└── platformStore.ts              # zustand: sidebar collapsed, route metadata
```

## Out of Scope

- Theming / light mode toggle.
- Internationalization beyond keeping mixed Chinese/English text the user already produces.
- Real-time updates to the workflows list when another tab makes changes (no websocket for list pages).
- Pagination of the runs / workflows lists. Default limits and a "Load more" pattern are deferred.
- Drag-to-resize for the three-pane workflow detail layout.
