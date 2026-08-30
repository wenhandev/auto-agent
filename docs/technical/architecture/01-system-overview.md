# 01 · 系统总览

## 1. 产品定位

**Auto Agent** 是一套 **Client-first** 的浏览器 / 桌面自动化平台：

| 角色 | 职责 |
|------|------|
| **云端控制面** | 认证、组织、工作流存储、调度、Worker 审批与分发、管理台 |
| **桌面客户端** | 日常执行：本地 Playwright、原生 Computer Use、录制、凭证、本地 LLM |
| **Web 管理台** | 组织管理、工作流查看/运行、Worker 审批、客户端下载（不做边缘创作） |

生产环境（`https://rpa.wenhandev.com`）以 `EXECUTION_BACKEND=control_plane_only` 运行：**云端不跑 Playwright**，实际浏览器与桌面操作发生在用户本机 Client / Worker。

---

## 2. 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  产品层                                                          │
│  ┌──────────────────┐              ┌──────────────────────────┐ │
│  │ Web Admin SPA    │              │ Auto Agent Client        │ │
│  │ (frontend/)      │              │ Tauri + React            │ │
│  └────────┬─────────┘              └────────────┬─────────────┘ │
└───────────┼─────────────────────────────────────┼───────────────┘
            │ HTTPS / Cookie                      │ HTTPS + Bearer
            │                                     │ + 本地 Runtime IPC
┌───────────▼─────────────────────────────────────▼───────────────┐
│  控制面 (backend FastAPI)                                        │
│  Auth · Orgs · Workflows · Runs · Triggers · Worker Hub · API v1 │
└───────────┬─────────────────────────────────────┬───────────────┘
            │ WSS /api/v1/workers/connect          │
            │                                      │
┌───────────▼──────────────┐         ┌─────────────▼──────────────┐
│  独立 Worker (可选)       │         │  嵌入式 Runtime Sidecar     │
│  auto-agent-worker start │         │  daemon / desktop-host      │
│  Playwright / Desktop    │         │  本地 Run · Draft · LLM     │
└──────────────────────────┘         └────────────────────────────┘
```

### 双执行模式

| `execution_backend` | 含义 |
|---------------------|------|
| `full` | 云端可直接执行 Playwright（本地开发默认） |
| `control_plane_only` | 云端仅调度/存储；Run 必须 `execution_mode=worker` |

由 `backend/app/services/control_plane_policy.py` 强制边界（禁止云端录制、浏览器会话、边缘凭证等）。

---

## 3. 仓库地图

```
auto_agent/
├── backend/          # FastAPI 控制面 + Agent + Worker 源码
├── frontend/         # 共享 React UI（Web + Desktop）
├── client/           # Tauri 2 桌面壳（alias 到 frontend/src）
├── worker/           # PyInstaller 打包脚本（sidecar 产物）
├── deploy/           # Docker / Caddy 生产部署
├── sdk/              # Python / TypeScript 公开 API 客户端
├── mcp/              # MCP Server（IDE 集成）
├── scripts/          # Smoke / E2E 脚本
├── openspec/         # 变更提案与规格
└── docs/technical/   # 本技术文档
```

---

## 4. 核心术语

| 术语 | 含义 |
|------|------|
| **Workflow** | 有向图：节点 + 边；版本不可变（`WorkflowVersion`） |
| **Run** | 一次执行实例；`mode=graph \| autonomous`；`execution_mode=cloud \| worker` |
| **Autonomous Task** | 目标驱动的 plan-act-observe 循环，不依赖预先画好的图 |
| **Worker** | 已注册执行设备；需 org 审批后才能接任务 |
| **Runtime / Sidecar** | 桌面内嵌 Python 进程（`:3921` 或 Unix socket IPC） |
| **Route Skill** | 按 URL/能力匹配的可复用技能 prompt；可由轨迹蒸馏提案后 adopt |
| **Computer Use** | 原生 OS 级桌面操作（AX/UIA），区别于 Playwright 浏览器自动化 |
| **Draft** | 本地工作流草稿（`~/.auto-agent-worker/drafts/`），可 pull/publish |

---

## 5. 两种主要用户路径

### 5.1 桌面本地运行（主路径）

1. 安装 Client → 登录云端 → 设备审批
2. 配置本地 LLM（加密存于 `~/.auto-agent-worker/llm.json`）
3. Run Console 选择工作流 → 本地 Runtime 执行 → SSE 事件 + 直播画面

### 5.2 云端调度到 Worker

1. Web/API 创建 Run（`execution_mode=worker`）
2. `worker_hub` 经 WSS 将 `execute` 帧分派给已批准、在线的 Worker
3. Worker 回传 `run_event` / 产物，控制面持久化并 fanout

---

## 6. 技术栈一览

| 层 | 技术 |
|----|------|
| 后端 | Python ≥3.11, FastAPI, SQLModel, APScheduler, Playwright, Google ADK / LiteLLM |
| Web UI | React 19, Vite, ReactFlow, Zustand, TanStack Query, i18n |
| 桌面 | Tauri 2 (Rust), 嵌入式 Python sidecar |
| 存储 | SQLite（默认 / 生产 volume）；Fernet 加密凭证 |
| 部署 | Docker Compose + Caddy (TLS) |
| 集成 | Python/TS SDK, MCP stdio |

---

## 7. 不变量（设计契约）

1. **工作流版本不可变**：Run 绑定 `workflow_version_id`，不直接改历史图。
2. **调度与语义分离**：`exec/scheduler.py` 管 DAG 就绪；`executor.py` 管节点语义。
3. **事件可观测**：`RunEvent.seq` 有序；WebSocket / SSE 订阅同一事件流。
4. **Worker 必须 approved** 且环境就绪，才能接本地或云端分派任务。
5. **控制面与边缘职责分离**：生产云端不做 Playwright / 桌面操作。
6. **凭证最小权限**：工作流通过 `WorkflowCredential` 显式关联可用凭证。

下一章：[02 · 后端架构](./02-backend.md)
