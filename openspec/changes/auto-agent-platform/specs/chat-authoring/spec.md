## ADDED Requirements

### Requirement: Per-Workflow Chat Session

Every `Workflow` SHALL be associated with exactly one `ChatSession`. The session SHALL be created lazily on the first chat read or write and SHALL persist for the lifetime of the workflow.

#### Scenario: Session is created on first read

- **WHEN** the frontend calls `GET /api/workflows/{id}` for a workflow that has no `ChatSession`
- **THEN** the backend SHALL create a `ChatSession` for it and the response SHALL include `chat_session_id`.

#### Scenario: Deleting workflow deletes session

- **WHEN** a workflow is deleted via `DELETE /api/workflows/{id}`
- **THEN** its `ChatSession` and all `ChatMessage` rows SHALL be removed in the same transaction.

### Requirement: Editor Agent As ADK LlmAgent

The chat editor SHALL be implemented as an ADK `LlmAgent` defined in `backend/app/agents/editor.py` with `output_schema=EditorResponse` (or the equivalent kwarg name in the installed ADK version) using the active LLM model returned by `get_adk_model_cached()`. The editor SHALL NOT use a separate per-purpose model; there is exactly **one** active `LlmConfig` shared across planner, editor, fuzzy, and extractor (see `runtime-llm-config`).

#### Scenario: Editor uses active LLM

- **WHEN** the editor agent is constructed for a turn
- **THEN** its `model` SHALL be the object returned by `get_adk_model_cached()` and SHALL NOT bypass the cache or instantiate provider SDKs directly.

#### Scenario: Structured output fallback

- **WHEN** the editor's structured output fails validation against `EditorResponse`
- **THEN** the turn SHALL retry once with a JSON-mode prompt parsed via `EditorResponse.model_validate_json`, and SHALL surface the validation error to the user as the assistant's `content` if both attempts fail.

### Requirement: Patch Op Set

`EditorResponse.patch` SHALL be a list of ops drawn from exactly this set, applied in order:

- `{op: "add_node", node: Node}`
- `{op: "remove_node", id: str}`
- `{op: "update_node", id: str, patch: {label?: str, type?: NodeType, params?: dict}}`
- `{op: "add_edge", edge: Edge}`
- `{op: "remove_edge", id: str}`
- `{op: "set_start", id: str}`

#### Scenario: Add a new node and wire it

- **WHEN** the editor returns `patch = [{op:"add_node", node:{id:"n7", type:"click", label:"点击购物车", params:{selector:".cart"}}}, {op:"add_edge", edge:{id:"e6", source:"n6", target:"n7"}}]` against a workflow that contains `n6` and has no incident edges leaving it
- **THEN** the patch SHALL apply cleanly, the resulting workflow SHALL contain both `n7` and `e6`, and a new `WorkflowVersion` SHALL be created.

#### Scenario: Remove a node also removes incident edges

- **WHEN** the editor returns `patch = [{op:"remove_node", id:"n3"}]` and `n3` is the target of `e2` and source of `e3`
- **THEN** both `e2` and `e3` SHALL be removed in the same atomic step, and the resulting workflow SHALL still validate (the editor is responsible for re-wiring if it wanted a chain; if it doesn't, an orphaned chain is acceptable as long as `start_id` still resolves).

#### Scenario: update_node merges params

- **WHEN** the editor returns `patch = [{op:"update_node", id:"n2", patch:{params:{value:"new"}}}]` against a node with `params = {selector:"#u", value:"old"}`
- **THEN** the resulting node SHALL have `params = {selector:"#u", value:"new"}` (deep-merge into `params`); `label` and `type` SHALL only change when explicitly provided in `patch`.

#### Scenario: set_start updates start_id

- **WHEN** the editor returns `patch = [{op:"set_start", id:"n2"}]` against a workflow that contains `n2`
- **THEN** the resulting workflow's `start_id` SHALL be `"n2"`.

#### Scenario: Unknown op rejected

- **WHEN** the editor returns an op whose `op` field is not one of the six allowed values
- **THEN** patch application SHALL fail with a clear error and no new version SHALL be written; the assistant message SHALL still be appended with `workflow_version_id=null` and the error text included in `content`.

### Requirement: Full Replacement Path

`EditorResponse.workflow` MAY be set instead of `patch` when the diff is too large to be sensibly expressed as a patch (typical case: the workflow is empty and the user just described it). At most one of `patch` and `workflow` SHALL be non-null per turn.

#### Scenario: First message bootstraps workflow

- **WHEN** the workflow's current version is empty (zero nodes) and the user describes a flow
- **THEN** the editor MAY return `workflow = <full Workflow JSON>` and the backend SHALL apply it as version 2 (or version 1 if no version existed yet).

#### Scenario: Both set is rejected

- **WHEN** `EditorResponse` is received with both `patch` and `workflow` non-null
- **THEN** the backend SHALL reject the response, retry once, and on second failure return a failed assistant message explaining the constraint.

### Requirement: Atomic Patch Application With Re-Validation

Patch application SHALL be performed on an in-memory copy. The result SHALL be re-validated against the `Workflow` pydantic model before any DB write. Only on successful validation SHALL a new `WorkflowVersion` row be inserted and `Workflow.current_version_id` advance.

#### Scenario: Invalid patch leaves DB unchanged

- **WHEN** a patch references a node id that does not exist (e.g. `remove_node` against `"n_missing"`) OR produces an unreachable `start_id`
- **THEN** patch application SHALL fail, no new version SHALL be written, `Workflow.current_version_id` SHALL be unchanged, and the assistant `ChatMessage` SHALL be appended with `patch_json` preserved and an error in `content`.

#### Scenario: Validation failure surfaces in chat

- **WHEN** the editor proposes nodes with a `type` outside `NodeType`
- **THEN** the appended assistant message SHALL include the validation error verbatim and SHALL invite the user to ask the editor to retry.

### Requirement: System Prompt For Editor Mode

The editor agent SHALL receive a system prompt that:

- Tells the model it is editing an existing `Workflow` and prefers patches over full replacements when possible.
- Lists the exact patch op set with one example per op.
- Enumerates the allowed `NodeType` values (mirroring `nl-workflow-planner`'s rules).
- Instructs the model to keep `label` text in the user's vocabulary.
- Instructs the model to set at most one of `patch` / `workflow` per turn and to leave both `null` for purely conversational turns ("yes I can do that, but should we also …?").

#### Scenario: Conversational turn

- **WHEN** the user asks "what does this workflow do?"
- **THEN** the editor MAY return `EditorResponse(content="<explanation>", patch=None, workflow=None)` and the backend SHALL append the assistant message without producing a new version.

### Requirement: Context Window Trimming

Each editor turn SHALL receive (a) the system prompt, (b) the current `WorkflowVersion.workflow_json` serialized as JSON, (c) the last N=20 `ChatMessage` rows (oldest discarded), (d) the new user message. If the resulting prompt exceeds a configurable char budget (default 60 000 chars), older messages SHALL be dropped until it fits.

#### Scenario: Long history is trimmed

- **WHEN** a chat session has 80 prior messages
- **THEN** the editor SHALL receive the most recent 20 (or fewer if char budget requires) and SHALL NOT receive any earlier messages.

### Requirement: Backwards-Compatible Generate Endpoint

`POST /api/workflow/generate` SHALL continue to accept `{description}` and return a `Workflow`. The platform implementation SHALL additionally:

1. Create a new `Workflow` row.
2. Create a `WorkflowVersion` row (#1) containing the planner's output.
3. Create a `ChatSession` and seed it with two `ChatMessage` rows: one `user` (`content=description`), one `assistant` (`content=<short summary>`, `workflow_version_id=<v1>`, `patch_json=null`).
4. Wrap the response: `{workflow_id, chat_session_id, workflow}`.

#### Scenario: Generate seeds chat

- **WHEN** `POST /api/workflow/generate` succeeds
- **THEN** the resulting workflow SHALL be visible in `GET /api/workflows` and `GET /api/chat/{session_id}` SHALL return at least one `user` and one `assistant` message.

## API contract

| Method | Path | Request | Response | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/api/chat/{session_id}` | — | `{messages: ChatMessage[]}` | full history |
| `POST` | `/api/chat/{session_id}/messages` | `{content: str}` | `{assistant_message: ChatMessage, new_version: WorkflowVersionSummary?, workflow?: Workflow}` | runs one editor turn |

`ChatMessage` shape:

```json
{
  "id": "msg_…",
  "session_id": "cs_…",
  "role": "assistant",
  "content": "Added a node to click the cart.",
  "patch_json": [{"op":"add_node","node":{"id":"n7", ...}}],
  "workflow_version_id": "ver_…",
  "created_at": "2026-…"
}
```

`POST /messages` response when a new version was produced:

```json
{
  "assistant_message": { ... ChatMessage ... },
  "new_version": {"id":"ver_…","version_number":4,"created_at":"…"},
  "workflow": { "nodes":[...], "edges":[...], "start_id":"n1" }
}
```

When the turn was purely conversational, `new_version` and `workflow` SHALL be omitted.

## Data model

```python
class EditorResponse(BaseModel):
    content: str
    patch: list[PatchOp] | None = None
    workflow: Workflow | None = None

class PatchOp(BaseModel):
    op: Literal["add_node","remove_node","update_node","add_edge","remove_edge","set_start"]
    # discriminated union; remaining fields depend on op
    node: Node | None = None
    edge: Edge | None = None
    id: str | None = None
    patch: dict | None = None
```

`patch.py` exposes `apply_patch(current: Workflow, ops: list[PatchOp]) -> Workflow` which makes a deep copy, mutates, re-validates, and returns the new `Workflow`.

## Out of Scope

- Mid-turn tool use by the editor (the editor never opens a browser; it only emits a patch). Running the workflow is a separate user action.
- Streaming the editor's response token-by-token. The endpoint returns the full assistant message at once.
- Branching chat sessions (one session per workflow).
- Reverting to an older version via chat (separate endpoint, deferred).
- Multi-user collaborative editing.
