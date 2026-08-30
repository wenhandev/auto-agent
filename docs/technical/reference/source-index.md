# 源码索引（速查）

## 后端

| 用途 | 路径 |
|------|------|
| 应用入口 | `backend/app/main.py` |
| 配置 | `backend/app/settings.py` |
| 数据模型 | `backend/app/db/models.py` |
| 工作流 Schema | `backend/app/schemas.py` |
| 执行器 | `backend/app/executor.py` |
| DAG 调度 | `backend/app/exec/scheduler.py` |
| Run 服务 | `backend/app/services/runs.py` |
| 自主任务 | `backend/app/services/tasks.py` / `agents/autonomous.py` |
| Worker Hub | `backend/app/services/worker_hub.py` |
| 控制面策略 | `backend/app/services/control_plane_policy.py` |
| 轨迹蒸馏 | `backend/app/services/trajectory_distillation.py` |
| Desktop CU | `backend/app/services/desktop_computer_use/` |
| Worker CLI/Daemon | `backend/app/worker/` |

## 前端 / 桌面

| 用途 | 路径 |
|------|------|
| Web 入口 | `frontend/src/main.tsx` |
| Web 路由 | `frontend/src/App.tsx` |
| Desktop 入口 | `frontend/src/client/main.tsx` |
| Desktop 路由 | `frontend/src/client/App.tsx` |
| 云端 API | `frontend/src/api-platform.ts` |
| Runtime 桥 (JS) | `frontend/src/client/runtimeBridge.ts` |
| Web 功能策略 | `frontend/src/lib/webPlatformPolicy.ts` |
| Tauri 宿主 | `client/src-tauri/src/lib.rs` |
| Runtime 桥 (Rust) | `client/src-tauri/src/runtime_bridge.rs` |
| OAuth 回调 | `client/src-tauri/src/oauth_callback.rs` |

## 打包 / 部署

| 用途 | 路径 |
|------|------|
| PyInstaller spec | `worker/auto-agent-worker.spec` |
| Stage sidecar | `worker/stage-client-sidecar.sh` |
| Docker | `deploy/Dockerfile`, `deploy/docker-compose.yml` |
| 生产 env 示例 | `deploy/.env.production.example` |

## SDK / MCP

| 用途 | 路径 |
|------|------|
| Python SDK | `sdk/python/auto_agent_sdk/` |
| TS SDK | `sdk/typescript/src/` |
| MCP | `mcp/auto_agent_mcp/` |
