## 1. Python SDK

- [x] 1.1 Create `sdk/python/auto_agent_sdk/` with `pyproject.toml` (independent versioning)
- [x] 1.2 `AutoAgent(base_url, api_key)` client with bearer auth
- [x] 1.3 Methods: `run_task`, `run_workflow`, `get_run`, `list_runs`, `cancel_run`, `wait`
- [x] 1.4 `workflows` / `credentials` sub-clients
- [x] 1.5 Pydantic models aligned to OpenAPI + a contract-drift test
- [x] 1.6 Thin async variant

## 2. CLI

- [ ] 2.1 `auto-agent` console-script entry point in the Python package
- [ ] 2.2 Commands: `run-task`, `run`, `runs`, `get [--watch]`, `cancel`
- [ ] 2.3 Key from env / 0600 config file; never echoed

## 3. TypeScript SDK

- [x] 3.1 Create `sdk/typescript/` ESM package with `package.json` + types
- [x] 3.2 `AutoAgent` client: `runTask`, `runWorkflow`, `getRun`, `cancelRun`, `waitForRun`
- [x] 3.3 Type declarations for all models

## 4. MCP server

- [x] 4.1 Create `mcp/` server wrapping the Python SDK
- [x] 4.2 Tools: `run_task`, `run_workflow`, `get_run`, `cancel_run`, `list_workflows`
- [x] 4.3 Env config validation + Cursor/Claude config snippet

## 5. Docs & examples

- [ ] 5.1 Per-SDK quick-start README
- [ ] 5.2 End-to-end example: run_task → poll → print outputs/artifacts
