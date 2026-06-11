## Description

Six new node types extend the executor with non-browser actions: `http_request`, `read_file`, `write_file`, `send_email`, `parse_json`, `parse_csv`. Each is a single deterministic action with a per-type pydantic params model and a documented output shape. The output shape is stable so downstream nodes can reference fields via `{{nodes.<id>.output.<path>}}` without conditional checks.

Filesystem access is sandboxed **per-workflow** to `backend/data/workflow_files/<workflow_id>/`. Absolute paths and traversal escapes are refused. Cross-workflow file sharing is explicitly out of scope — workflows that need shared data MUST copy it via `subworkflow` (or manually). HTTP egress is unrestricted (single-user POC). Credentials are interpolated through the existing `{{cred...}}` token form; SMTP login uses a credential whose fields conventionally include `{host, port, username, password, use_tls}`.

## User stories

- **As a workflow author**, I want to call an internal API to fetch a JSON payload and pipe one of its fields into a subsequent `navigate` URL.
- **As a workflow author**, I want to read a CSV file from a known directory, parse it, and run my existing workflow per row.
- **As a workflow author**, I want to email a one-line confirmation after a successful run completes.
- **As a workflow author**, I want a `4xx` HTTP response to be observable (so my next node can branch on it) instead of silently failing the run.
- **As an operator**, I want file access confined to a single workspace dir so a buggy workflow cannot read my SSH keys.

## Functional requirements

### Requirement: `http_request` Node

The `NodeType` literal SHALL include `"http_request"`. Its params SHALL validate against:

```python
class HttpRequestParams(BaseModel):
    method: Literal["GET","POST","PUT","DELETE","PATCH","HEAD"]
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    body_kind: Literal["json","text","form","none"] = "json"
    timeout_ms: int = Field(default=15_000, ge=1, le=120_000)
```

The action SHALL issue the HTTP request via `httpx.AsyncClient` and return `{status: int, headers: dict[str,str], json: Any|null, text: str, elapsed_ms: int}`. `json` SHALL be populated iff the response's `content-type` matches `application/json` AND the body parses. `text` SHALL be populated unconditionally, truncated to 1 MB with `text_truncated: true` added when truncation occurs. `4xx` / `5xx` responses SHALL NOT raise; only network errors (DNS, refused, TLS, timeout) SHALL raise. Credentials in `headers` (e.g. `Authorization: Bearer {{cred.api.token}}`) SHALL resolve via the existing credential interpolation pass.

#### Scenario: GET returning JSON

- **WHEN** an `http_request` node with `method="GET", url="https://api.example.com/order/42"` is run and the server returns 200 with `application/json` body `{"id":42,"status":"shipped"}`
- **THEN** the node's `output` SHALL equal `{"status":200, "headers":{"content-type":"application/json", ...}, "json":{"id":42,"status":"shipped"}, "text":"{\"id\":42,\"status\":\"shipped\"}", "elapsed_ms":<int>}`.

#### Scenario: 4xx returns completion not failure

- **WHEN** the same URL returns 404
- **THEN** the node SHALL emit `node_completed` (NOT `node_failed`) AND `output.status` SHALL be `404`.

#### Scenario: Network error raises

- **WHEN** the URL resolves but the connection is refused
- **THEN** the node SHALL raise (caught by the executor as `node_failed`) AND its error SHALL identify the network failure.

#### Scenario: Authorization header from credential

- **WHEN** `headers={"Authorization":"Bearer {{cred.api.token}}"}` and the credential is linked + has field `token`
- **THEN** the resolved request SHALL carry the decrypted token AND the plaintext SHALL NOT appear in any persisted event.

### Requirement: `read_file` And `write_file` Nodes — Per-Workflow Sandbox

The `NodeType` literal SHALL include `"read_file"` and `"write_file"`. Both SHALL resolve their `path` parameter against the **per-workflow** dir `WORKSPACE_DIR / <workflow_id>/`, where `WORKSPACE_DIR = backend/data/workflow_files/`. Both SHALL refuse paths that are absolute (per `Path.is_absolute()`), and SHALL refuse paths whose resolved absolute path is outside the per-workflow dir after `Path.resolve()` normalisation. `read_file` SHALL enforce `max_bytes: int = 1_048_576` (1 MB default, 10 MB cap); reads exceeding the cap SHALL raise `ValueError`. `write_file` SHALL create parent directories WITHIN the per-workflow sandbox as needed and SHALL overwrite existing files. The top-level `WORKSPACE_DIR` SHALL be created on first boot by a lifespan helper; per-workflow subdirs SHALL be created lazily on first file-action use.

Both actions SHALL raise `SandboxViolation("file actions require a persisted workflow")` when invoked without a `workflow_id` (i.e. via the legacy `/ws/run` ad-hoc workflow-payload path). The persisted-run path (`POST /api/runs`) SHALL always provide the run's `workflow_id`.

When a workflow is deleted (`DELETE /api/workflows/{id}`), its per-workflow sandbox dir SHALL be removed in the same operation via best-effort `shutil.rmtree(..., ignore_errors=True)`. Failures SHALL be logged at `WARNING` but SHALL NOT block the API response.

Cross-workflow file sharing is **explicitly out of scope**. A workflow that needs data produced by another workflow MUST either invoke the producing workflow via `subworkflow` and consume its output via `{{nodes.<sub>.output.final_output...}}`, or the operator MUST manually copy files between sandboxes using their OS file manager. There is NO API endpoint and NO action that allows one workflow to read another workflow's sandbox.

Params:

```python
class ReadFileParams(BaseModel):
    path: str
    encoding: str = "utf-8"
    max_bytes: int = Field(default=1_048_576, ge=1, le=10_485_760)

class WriteFileParams(BaseModel):
    path: str
    contents: str  # may include {{nodes...}} tokens resolved before write
    encoding: str = "utf-8"
```

Outputs:

```python
# read_file
{"contents": str, "byte_count": int, "path": str}  # path is the resolved workspace-relative path

# write_file
{"path": str, "byte_count": int}
```

#### Scenario: Round-trip write then read

- **WHEN** a workflow writes `"hello"` to `path="t.txt"` and a subsequent `read_file` reads `path="t.txt"`
- **THEN** the read's `output.contents` SHALL equal `"hello"` AND the file SHALL exist at `backend/data/workflow_files/<this_workflow_id>/t.txt`.

#### Scenario: Per-workflow isolation

- **WHEN** workflow A writes `"hello-A"` to `path="t.txt"` and workflow B then runs `read_file(path="t.txt")`
- **THEN** workflow B's `read_file` SHALL raise `FileNotFoundError` (translated to `node_failed`) because workflow B's sandbox is `WORKSPACE_DIR / <B_id>/`, NOT workflow A's sandbox. Cross-workflow access SHALL NOT be possible through any file-action parameter.

#### Scenario: Absolute path refused

- **WHEN** `path="/etc/passwd"` on POSIX or `path="C:\\Windows\\System32\\drivers\\etc\\hosts"` on Windows
- **THEN** the action SHALL raise `SandboxViolation("absolute paths refused")` AND the executor SHALL emit `node_failed`.

#### Scenario: Path traversal refused

- **WHEN** `path="../../etc/passwd"` (or any sequence that resolves outside the per-workflow sandbox)
- **THEN** the action SHALL raise `SandboxViolation(...)`.

#### Scenario: Ephemeral run refused

- **WHEN** a `read_file` or `write_file` action is invoked via the legacy `/ws/run` workflow-payload path (no persisted `Run`, `workflow_id=None`)
- **THEN** the action SHALL raise `SandboxViolation("file actions require a persisted workflow")` AND the executor SHALL emit `node_failed`.

#### Scenario: Workflow delete cascades sandbox

- **WHEN** `DELETE /api/workflows/{id}` is called for a workflow whose sandbox dir contains files
- **THEN** the sandbox dir SHALL be removed via best-effort `shutil.rmtree(..., ignore_errors=True)` in the same operation AND the API SHALL return 200 even if the deletion partially fails (a `WARNING` SHALL be logged in that case).

#### Scenario: max_bytes enforced

- **WHEN** the file on disk is 5 MB and `max_bytes=1_048_576`
- **THEN** the action SHALL raise `ValueError` AND SHALL NOT load the full file into memory.

### Requirement: `send_email` Node

The `NodeType` literal SHALL include `"send_email"`. Params:

```python
class SendEmailParams(BaseModel):
    smtp_credential: str           # name; resolved against the credential vault
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    body_kind: Literal["text","html"] = "text"
    attachments: list[str] = Field(default_factory=list)
```

The action SHALL look up the credential by `smtp_credential` (via the existing per-workflow link enforcement); its fields are conventionally `{host, port, username, password, use_tls}` (the action SHALL fail with a clear error if any of host/port/username/password is missing). Attachments SHALL be resolved via the sandbox. The action SHALL send via `aiosmtplib`, optionally over TLS per `use_tls`. Output:

```python
{"message_id": str, "accepted": list[str], "rejected": list[str]}
```

#### Scenario: Happy send

- **WHEN** a credential `corp-smtp` carries valid fields and a `send_email` node addresses `to=["alice@x"]`
- **THEN** the action SHALL return `{"message_id":"<uuid>", "accepted":["alice@x"], "rejected":[]}`.

#### Scenario: Missing field

- **WHEN** the credential lacks the `password` field
- **THEN** the action SHALL raise with a message naming the missing field AND the executor SHALL emit `node_failed`.

#### Scenario: Attachment outside per-workflow sandbox

- **WHEN** an `attachments` entry resolves outside this workflow's sandbox dir (`WORKSPACE_DIR / <workflow_id>/`) — including the case where it points at another workflow's sandbox
- **THEN** the action SHALL raise `SandboxViolation(...)` BEFORE opening the SMTP connection.

### Requirement: `parse_json` And `parse_csv` Nodes

The `NodeType` literal SHALL include `"parse_json"` and `"parse_csv"`. Both are pure transforms; they do not touch the filesystem or the network.

Params and outputs:

```python
class ParseJsonParams(BaseModel):
    input: Any   # typically a token resolved to a string

class ParseCsvParams(BaseModel):
    input: Any
    has_header: bool = True
    delimiter: str = ","

# parse_json output
{"parsed": Any}

# parse_csv output
{"rows": list[dict|list], "header": list[str]|null}
```

`parse_csv` with `has_header=True` SHALL return `rows` as `list[dict]` keyed by header values; `has_header=False` SHALL return `rows` as `list[list[str]]` and `header=null`. Malformed input SHALL raise `ValueError`.

#### Scenario: Parse JSON round-trip

- **WHEN** `input='{"a":1,"b":[2,3]}'`
- **THEN** the output SHALL be `{"parsed": {"a": 1, "b": [2, 3]}}`.

#### Scenario: Parse CSV with header

- **WHEN** `input="id,name\n1,foo\n2,bar\n"` and `has_header=true`
- **THEN** the output SHALL be `{"rows": [{"id":"1","name":"foo"},{"id":"2","name":"bar"}], "header":["id","name"]}`.

### Requirement: Stable Output Shapes

The output schemas listed above SHALL be the contract downstream nodes rely on. Optional fields SHALL be `null` rather than absent when not applicable. Truncation indicators SHALL use distinct boolean fields (e.g. `text_truncated: true`) so downstream conditions can branch on them.

#### Scenario: HTTP non-JSON response

- **WHEN** the server returns 200 with `text/html` body
- **THEN** `output.json` SHALL be `null` AND `output.text` SHALL contain the HTML AND a downstream `condition` checking `{{nodes.<http>.output.json}}` against `null` SHALL be authoritative.

### Requirement: Editor / Planner Catalogue Knows Each Type

The editor agent's and planner agent's system prompts SHALL document each of the six new types with one example per type (params shape + output shape). The example SHALL use the `{{cred...}}` and `{{nodes...}}` token forms where appropriate.

#### Scenario: Editor emits a valid http_request

- **WHEN** the user asks the editor "添加一个 HTTP 节点 GET https://api.example.com/orders, 用 Bearer token"
- **THEN** the editor SHALL emit an `add_node` patch whose `node.type == "http_request"` AND whose params include the URL and an `Authorization` header referencing a credential.

## API contract

No new HTTP endpoints. The dispatcher's input is `Workflow` JSON; the new node types are valid values for `Node.type`. Per-type params validation happens at workflow save / chat-editor-apply time.

## Data model

No DB schema change for this capability. All additions are inside `WorkflowVersion.workflow_json`.

The action surface lives in `backend/app/tools/`:

```
actions_http.py    — http_request(params)
actions_files.py   — read_file(params, *, workflow_id), write_file(params, *, workflow_id)
actions_email.py   — send_email(params, session, *, workflow_id)
actions_parse.py   — parse_json(params), parse_csv(params)
sandbox.py         — WORKSPACE_DIR, workflow_dir(workflow_id), resolve_sandbox_path(path, *, workflow_id), SandboxViolation
```

`workflow_id` is threaded into file-touching actions by the executor dispatch site (from `Run.workflow_id`); ephemeral `/ws/run` invocations pass `None` and those actions raise `SandboxViolation` accordingly.

## Out of Scope

- Streaming / chunked HTTP responses; the body is fully buffered up to the 1 MB text cap.
- HTTP/2 push, WebSocket actions, gRPC.
- SFTP / S3 / cloud-storage file nodes. Local sandbox only.
- CSV writing back to a file. Only reading in v1.
- Templated email bodies (use `node-context-variables` + a literal string `body`).
- Cross-workflow file sharing (the v1 sandbox is per-workflow; explicit `subworkflow` is the only intended path for shared data).
- HTTP egress allowlists.
- TLS pinning, mutual TLS, client certificates for the HTTP node.
- A database query node (separate change later).
- Arbitrary OS command execution (security boundary).
