# 09 · SDK 与 MCP

对公开 REST **`/api/v1`** 的薄封装，风格接近 Skyvern（`runTask` / `getRun` / poll `wait`）。  
设计见 `openspec/changes/sdk-and-mcp/design.md`。

## 1. Python SDK

路径：`sdk/python/auto_agent_sdk/`

| 模块 | 说明 |
|------|------|
| `client.py` | 同步 `AutoAgent` |
| `async_client.py` | 异步 `AsyncAutoAgent` |
| `workflows.py` / `credentials.py` | 子客户端 |
| `cli.py` | CLI `auto-agent` |
| `models.py` / `config.py` | 模型与配置 |

认证：`AUTO_AGENT_BASE_URL` + `AUTO_AGENT_API_KEY`（`Authorization: Bearer`）。

| 方法 | HTTP |
|------|------|
| `run_task(...)` | `POST /api/v1/run-task` |
| `run_workflow(id, parameters=...)` | `POST /api/v1/workflows/{id}/run` |
| `get_run` / `list_runs` / `cancel_run` | `/api/v1/runs…` |
| `wait(...)` | 轮询至终态 |
| `workflows.list` / `credentials.list` | 列表 |

CLI：`run-task`、`run-workflow`、`get-run`、`list-runs`、`cancel-run`（支持 `--watch`、`--json`）。

---

## 2. TypeScript SDK

路径：`sdk/typescript/src/`

- `AutoAgent`（`client.ts`）、`WorkflowsClient`、`HttpTransport`
- API 面与 Python 对齐；`runWorkflow` 可带 `browserSessionId`
- 构建：`npm run build`；测试 vitest

---

## 3. MCP Server

路径：`mcp/auto_agent_mcp/`

为 Cursor / Claude Desktop 等提供 **stdio** MCP 工具，内部委托 Python SDK。

| MCP Tool | 对应 |
|----------|------|
| `run_task` | `client.run_task` |
| `run_workflow` | `client.run_workflow` |
| `get_run` / `cancel_run` | runs |
| `list_workflows` | workflows.list |

启动：`python -m auto_agent_mcp.server` 或 `auto-agent-mcp`。

配置示例：`mcp/cursor-config.json`（注入 `AUTO_AGENT_BASE_URL` / `AUTO_AGENT_API_KEY`）。

---

## 4. 与产品边界

- SDK/MCP 走**云端公开 API**，执行仍受 `execution_backend` 与 Worker 可用性约束。
- 本地 sidecar 草稿/本地 Run **不是** SDK 的目标面；那是 Desktop Runtime API。

下一章：[10 · 路线图与 OpenSpec](./10-roadmap.md)
