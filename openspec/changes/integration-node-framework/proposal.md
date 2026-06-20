## depends_on

- `expanded-node-library` — the `http_request` node and the `app/nodes/` module layout this framework wraps and generalises.
- `items-data-model` — integration operations consume `input_items` and emit `items` (one item per record/result).
- `expression-engine` / `node-context-variables` — operation parameters use tokens/expressions.
- `per-workflow-credentials` — the existing credential vault and `{{cred.<name>.<field>}}` interpolation that typed credentials extend.

Hard prerequisite for `core-app-integrations` (Slack/Gmail/Sheets/Notion are descriptors on this framework). No browser dependency.

## Why

n8n has 400+ app integrations, but they are not 400 bespoke nodes — they are **descriptors** over a generic HTTP execution core: each app declares its `resources`, each resource its `operations`, each operation its fields and how they map to an HTTP request, plus a typed credential that injects auth. auto-agent has a raw `http_request` node but no structured way to add "an app with operations". Without this framework, every integration would be a hand-written node and credentials would stay untyped key-value blobs. This change builds the **framework** (descriptor schema + generic executor + typed credentials + a declarative node UI), so apps become data, not code.

## What Changes

- **Integration descriptor schema**: an app is described by `{ app, version, credentials[], resources[] }`; a resource has `operations[]`; an operation declares `{ name, fields[], request, response }` where `request` is a declarative HTTP template (method, url template, query, headers, body) referencing field values and credential values, and `response` declares how to map the HTTP response into output `items` (`root_path`, `item_path`, pagination).
- **Typed credentials**: extend `per-workflow-credentials` from free key-value to typed credential *types* (`{ type, fields[] }` with field kinds `string|secret|oauth2`) and an **auth injection** spec: `api_key_header`, `api_key_query`, `bearer`, `basic`, or `oauth2` (authorization-code + client-credentials; token storage + refresh). A descriptor's operation references a credential type; the framework injects auth at request time. Secrets stay in the existing encrypted vault.
- **Generic integration node** `integration`: params `{ app, resource, operation, fields }`. The executor resolves the matching descriptor, renders the declarative request (with token/expression interpolation + credential injection), executes it (reusing the `http_request` transport: retries, timeout, redirect policy), and maps the response into `items` per the descriptor's `response` spec. Pagination iterates and concatenates pages up to a cap.
- **Declarative UI generation**: the NodeInspector renders an integration node's form from the descriptor (resource dropdown → operation dropdown → field inputs with types), so a new app needs no frontend code.
- **OAuth2 connect flow**: a backend route initiates the OAuth2 authorization-code flow, stores the token in the vault, and refreshes on expiry. A "Connect <app>" button in the credential UI drives it.
- **Descriptor registry + validation**: descriptors live as data (JSON/py) under `app/integrations/`; a loader validates them at startup; a test harness can exercise an operation against a recorded fixture.
- **Editor / planner prompts**: the planner can pick `integration` with `{app, resource, operation}` from the registry's catalogue.

## Capabilities

### New Capabilities

- `integration-descriptor`: the descriptor schema (app/resource/operation/field/request/response/pagination), the loader + registry, and descriptor validation.
- `generic-integration-executor`: the `integration` node, declarative request rendering + credential injection, response→items mapping, pagination, and reuse of the `http_request` transport.
- `typed-credentials`: typed credential types, the auth-injection strategies (`api_key`/`bearer`/`basic`/`oauth2`), the OAuth2 connect/refresh flow, and the declarative credential UI.

### Modified Capabilities

- `non-browser-action-nodes` (from `expanded-node-library`): `http_request`'s transport (retry/timeout/redirect/error mapping) is factored into a reusable client the framework calls.
- `credential-vault` / `per-workflow-credentials`: credentials gain a `type` and typed fields; untyped key-value credentials remain supported (a `generic` type).
- `workflow-schema` (from `auto-agent-mvp`): `NodeType` gains `integration`.
- `chat-authoring` / `nl-workflow-planner`: the registry catalogue is surfaced to the planner.

## Impact

- **Backend**: `app/integrations/` (descriptor models, loader, registry); `app/nodes/integration.py` (generic executor); an `http_client` extracted from `http_request`; credential-type models + auth injectors + OAuth2 routes (`/api/oauth2/<app>/connect`, `/callback`); descriptor validation + a fixture-replay test harness. ~700 LOC + ~400 LOC tests. DB: credentials table gains a `type` column + `oauth_tokens` table (migration).
- **Frontend**: descriptor-driven node form, credential-type forms, "Connect <app>" OAuth flow UI. ~500 LOC.
- **Runtime**: one HTTP call per operation (plus pagination pages, capped); OAuth refresh on demand.
- **Security**: secrets and OAuth tokens stay in the encrypted vault; descriptors never contain secrets; the request renderer must not log secret-bearing headers (redaction in run events).
- **Migration**: additive node type; credential `type` defaults to `generic` for existing rows; new `oauth_tokens` table.
- **Out of scope**: shipping specific apps (that is `core-app-integrations`); a visual descriptor builder (descriptors are authored as data); webhook/trigger sides of apps (that is `polling-and-app-triggers`); GraphQL/SOAP transports (REST/JSON first); a 400-app catalogue (we build the framework + a handful via the sibling change).
