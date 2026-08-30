# Auto Agent 技术文档

> 基于仓库源码梳理的完整技术文档。覆盖控制面、桌面客户端、执行运行时、部署与 SDK。
>
> 生成日期：2026-07-18

## 文档导航

| 文档 | 内容 |
|------|------|
| [01 · 系统总览](./architecture/01-system-overview.md) | 产品定位、分层架构、仓库地图、核心术语 |
| [02 · 后端架构](./architecture/02-backend.md) | FastAPI 入口、服务层、Agent、执行引擎、API |
| [03 · 数据模型](./architecture/03-data-models.md) | SQLModel 实体、关系、Run/Workflow 生命周期 |
| [04 · 执行流](./architecture/04-execution-flows.md) | 工作流 Run、自主任务、Worker 分发、事件流 |
| [05 · 前端与桌面](./architecture/05-frontend-desktop.md) | Web/Desktop 双壳、Tauri、Runtime 桥接 |
| [06 · Worker 与 Runtime](./architecture/06-worker-runtime.md) | Sidecar、daemon、desktop-host、打包 |
| [07 · 桌面 Computer Use](./architecture/07-desktop-computer-use.md) | 原生桌面自动化、授权、感知、节点 |
| [08 · 部署与运维](./architecture/08-deploy.md) | 控制面 Docker、Caddy、客户端发布 |
| [09 · SDK 与 MCP](./architecture/09-sdk-mcp.md) | Python/TS SDK、MCP 工具 |
| [10 · 路线图与 OpenSpec](./architecture/10-roadmap.md) | 进行中变更与演进关系 |
| [11 · Desktop browser-agent loop](./architecture/11-desktop-browser-agent.md) | 编号 tree / set-of-marks / Take control |
| [源码索引](./reference/source-index.md) | 关键文件路径速查 |

### 快速上手（开发）

```bash
# 终端 1 — 云端 / 本地控制面
cd backend && source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001

# 终端 2 — 桌面客户端（自动拉起 sidecar）
cd client && npm install && npm run tauri:dev
```

Web 管理台：`cd frontend && npm run dev`（默认代理到 backend）。

生产控制面：见 [08 · 部署与运维](./architecture/08-deploy.md)。

## 阅读建议

1. 先读 **系统总览**，建立「控制面 ↔ 桌面执行面」心智模型。
2. 做后端/Agent 开发 → **后端** + **数据模型** + **执行流**。
3. 做 UI / 桌面壳 → **前端与桌面** + **Worker Runtime**。
4. 做原生桌面自动化 → **Desktop Computer Use**。
5. 做发布/运维 → **部署** + **Worker 打包**。

## 源码与既有 README

| 路径 | 说明 |
|------|------|
| [`README.md`](../../README.md) | 仓库入口（含历史 POC 说明） |
| [`backend/README.md`](../../backend/README.md) | 后端本地开发 |
| [`client/README.md`](../../client/README.md) | 桌面客户端（主产品路径） |
| [`worker/README.md`](../../worker/README.md) | Sidecar 打包 |
| [`deploy/README.md`](../../deploy/README.md) | 生产部署 |
| [`openspec/changes/`](../../openspec/changes/) | 变更提案与规格 |

---

本文档描述的是当前代码库的**实际架构**；历史 POC（纯本地 Playwright demo）仍保留在 README 中，但产品主路径已是 **Client-first + Control Plane**。
