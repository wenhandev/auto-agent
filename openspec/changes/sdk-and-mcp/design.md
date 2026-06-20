## Context

`public-api-and-auth` defines a versioned, authed `/api/v1` surface with a curated OpenAPI document. SDKs and the MCP server are thin clients over it. Skyvern's clients are deliberately minimal — `runTask`, `getRun`, wait helpers — so we match that ergonomics rather than building a heavy abstraction.

## Goals / Non-Goals

**Goals:**
- One-import ergonomics in Python and TypeScript.
- An MCP server so AI IDEs can drive `auto-agent`.
- A CLI for scripts/CI.

**Non-Goals:**
- Event-stream subscription in clients (poll-only v1).
- Publishing pipelines (PyPI/npm release is ops, not this change).
- Multi-language codegen beyond Python/TS.

## Decisions

### Decision 1: Thin hand-written clients, models aligned to OpenAPI
Clients are small hand-written wrappers; request/response models are kept in lockstep with the OpenAPI contract (generated or hand-mirrored, with a test asserting they match).
- **Why**: a thin wrapper is more ergonomic than raw generated code; a contract test prevents drift.
- **Alternative rejected**: fully generated SDKs (clunky surface, poor naming).

### Decision 2: Poll-based `wait`/`--watch`, not WS
`wait(run, timeout)` polls `GET /api/v1/runs/{id}` with backoff to a terminal status.
- **Why**: v1 simplicity; no auth-over-WS to design yet. A streaming `run.stream()` is future.

### Decision 3: MCP server is a separate process wrapping the SDK
The MCP server imports the Python SDK and exposes tools; it reads base URL + key from env.
- **Why**: reuse the SDK; keep the MCP layer tiny. Ships a Cursor/Claude config snippet.

### Decision 4: CLI lives in the Python SDK package
`auto-agent` console-script entry point reuses the Python client.
- **Why**: one install (`pip install auto-agent-sdk`) gives both library and CLI.

### Decision 5: Independent versioning
SDK/MCP packages version independently from the backend; they target a `/api/v1` major.
- **Why**: clients evolve at a different cadence than the server.

## Risks / Trade-offs

- [Contract drift between SDK models and API] → a contract test in CI compares SDK models against the served OpenAPI.
- [Poll latency for long runs] → backoff polling + `--watch` UX; streaming deferred.
- [MCP env misconfig] → the server validates `AUTO_AGENT_BASE_URL`/`API_KEY` on start and prints actionable errors.
- [Secret handling in CLI] → key read from env or a config file with 0600 perms; never echoed.

## Migration Plan

- New packages added; no backend change.
- Document the three install paths (Python, TS, MCP) and the IDE config snippet.

## Open Questions

- Bundle the MCP server into the Python SDK package vs. a standalone package? (Lean: standalone `mcp/` for clean dependencies.)
- Provide an async-first Python client or sync-first with an async shim? (Lean: sync-first + thin async, matching most scripting use.)
