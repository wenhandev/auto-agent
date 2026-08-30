# 02 · 后端架构

路径：`backend/`。技术栈：**FastAPI + SQLModel + Playwright + Google ADK/LiteLLM + APScheduler**。

## 1. 目录结构

```
backend/app/
├── main.py                 # FastAPI 应用、lifespan、路由挂载、WS
├── settings.py             # Pydantic Settings（.env）
├── executor.py             # 节点语义执行、自愈、审批
├── exec/scheduler.py       # DAG indegree 调度
├── schemas.py              # Workflow / Node / Edge
├── schemas_tasks.py        # 自主任务 TaskSpec / TaskResult
├── schemas_api.py          # REST DTO
├── db/                     # models, session, migrations, crypto
├── agents/                 # Planner / Autonomous / Desktop / Distiller …
├── services/               # 业务服务
├── routers/                # HTTP 路由
├── auth/                   # Session / API Key / Worker Token / RBAC
├── tools/                  # Playwright 动作、浏览器池、沙箱
├── nodes/                  # 数据流节点（items 模型）
├── integrations/           # Gmail / Slack / Notion 等插件
├── worker/                 # 本地 Worker / Desktop Runtime
└── workflows/              # 内置示例工作流
```

---

## 2. 入口：`main.py`

### 2.1 Lifespan 启动序列

1. `init_db()` + 大量 `ensure_*` 增量迁移
2. 组织 bootstrap、Worker 表、OAuth 域规则
3. 加载 Fernet 密钥、集成插件 `load_integrations()`
4. 清理丢失审批、过期 browser session、**失败所有 in-flight runs**
5. 种子示例工作流
6. `run_svc.set_main_loop()`、`scheduler_svc.init_scheduler()`、Webhook 重载
7. `browser_session_svc.start_reaper()`

关闭时：非 `control_plane_only` 则关闭 Playwright；关闭调度器。

### 2.2 中间件

- **CORS**：`settings.cors_origins` + 固定桌面 origins（`DESKTOP_CLIENT_CORS_ORIGINS`，含 Tauri / `:8745`）

### 2.3 WebSocket

| 路径 | 用途 |
|------|------|
| `/ws/run` | 订阅已有 run 或即时执行 workflow JSON |
| `/ws/stream/{run_id}` | CDP screencast 直播 |

---

## 3. Agent 层（`app/agents/`）

| Agent | 文件 | 职责 |
|-------|------|------|
| **Planner** | `planner.py` | NL → 严格 `Workflow` JSON（ADK LlmAgent） |
| **Fuzzy / Vision** | `fuzzy.py`, `vision.py` | 页面感知驱动的工具调用 |
| **Synthesizer** | `synthesizer.py` | 录制 trace → 规则合成工作流 |
| **Distiller** | `distiller.py` | 录制/轨迹 → LLM 或规则蒸馏 |
| **Autonomous** | `autonomous.py` | plan-act-observe-reflect 循环 |
| **Desktop** | `desktop.py` | 原生桌面 observe→act |
| **Model** | `model.py` | Gemini / LiteLLM 统一工厂 |

### Autonomous 循环（要点）

```
reflect → plan
  while budget:
    perceive → match route_skill → decide(LLM) → execute tool
    guardrails（域限制、确认门、进度、连续错误 → re-reflect）
  finish → TaskResult
```

护栏见 `autonomous_guardrails.py`（`BudgetClock`、`ProgressTracker`、`ConfirmationGate`）。

---

## 4. 执行引擎

| 模块 | 职责 |
|------|------|
| `executor.py` | 节点语义、插值、Playwright/vision/desktop、重试、自愈、审批 |
| `exec/scheduler.py` | DAG indegree 就绪队列；condition/switch 边选择 |
| `services/runtime_engine.py` | `execute_run()`：cloud/worker 统一包装 |
| `services/runs.py` | 全局队列、dispatcher、fanout、abort |
| `services/tasks.py` | 自主任务队列与驱动 |
| `services/scheduler.py` | APScheduler → `enqueue_run` |

节点类型定义见 `schemas.py` 的 `NodeType`（含 `navigate`/`fuzzy_action`/`vision_*`/`desktop_*`/`condition`/`foreach`/`login`/`approval` 等）。

---

## 5. 关键服务（`app/services/`）

| 服务 | 职责 |
|------|------|
| `runs` / `tasks` | Run / 自主任务生命周期 |
| `worker_hub` | Worker WebSocket 连接池与任务分派 |
| `workers` | Worker 注册、审批状态 |
| `control_plane_policy` | 控制面模式策略门禁 |
| `trajectory_distillation` | 轨迹 → RouteSkillProposal |
| `route_skills` / `route_skill_proposals` | 匹配、adopt、dismiss |
| `perception` / `desktop_perception` | 页面 / 桌面感知 |
| `desktop_computer_use/` | 原生桌面后端（macOS/Windows/fake） |
| `artifacts` / `livestream` | 产物与 CDP 直播 |
| `approvals` | 人机审批挂起 |
| `credential_service` | 凭证解析与插值 `{{cred.*}}` |
| `browser_*` | Profile / Session / Pool / Provider |
| `chat` | 工作流 AI 辅助编辑 |

---

## 6. API 路由概览

### 内部 UI（`/api/*`，Session Cookie / Bearer）

| 前缀 | 说明 |
|------|------|
| `/api/auth`, `/api/auth/oauth/*` | 登录、OAuth |
| `/api/workflows`, `/api/runs`, `/api/tasks` | 工作流与执行 |
| `/api/recordings` | 录制与合成/蒸馏 |
| `/api/route-skills`, `/api/route-skill-proposals` | 技能与提案 |
| `/api/credentials`, `/api/browser-*` | 凭证与浏览器资源 |
| `/api/triggers`, `/api/webhooks` | 调度与出站 Webhook |
| `/api/workers` | UI 侧 Worker 管理 |
| `/api/admin`, `/api/orgs`, `/api/settings` | 管理与组织 |
| `/api/llm-config` | LLM 配置 |

遗留 demo：`GET /api/sample-workflow`、`POST /api/workflow/generate`、`GET /api/health`。

### 公开 v1（`/api/v1/*`，API Key）

- `run-task`、runs、workflows、credentials、keys
- Worker：`/api/v1/workers/login`、`/connect`（WSS）等

OpenAPI 对 `/api/v1` 注入 `BearerAuth` / `x-api-key` security schemes。

---

## 7. 认证与授权

| 机制 | 位置 |
|------|------|
| Session JWT / Cookie | `auth/session.py` |
| API Key | `auth/api_key.py` |
| RBAC（viewer→owner + workflow visibility） | `auth/authorization.py` |
| Worker Token | `auth/worker_auth.py` |
| 平台 OAuth（Google，支持 desktop 回调） | `routers/oauth_login.py` |
| 集成 OAuth（Gmail/Slack…） | `routers/oauth2.py` |

---

## 8. 配置要点（`settings.py`）

| 配置 | 说明 |
|------|------|
| `execution_backend` | `full` \| `control_plane_only` |
| `llm_provider` / `*_api_key` / `*_model` | LLM |
| `browser_*` / `max_concurrent_browser_runs` | 浏览器池 |
| `computer_use_enabled` | Playwright 坐标 fallback（与原生 Desktop CU 不同） |
| `credential_backend` | `local` \| `env` \| `vault` |
| `database_url` | 默认 SQLite |
| `oauth_*` / `cors_origins` / `session_secret` | 安全与登录 |
| `worker_heartbeat_*` | Worker 心跳 |

完整模板见 `backend/.env.example` 与 `deploy/.env.production.example`。

---

## 9. 依赖与 CLI

- 包入口：`backend/pyproject.toml`
- Worker CLI：`auto-agent-worker` → `app.worker.cli:main`
- 可选 extras：`desktop-macos`、`desktop-windows`、`worker-build`（PyInstaller）

下一章：[03 · 数据模型](./03-data-models.md)
