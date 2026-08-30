# 10 · 路线图与 OpenSpec

OpenSpec 变更目录：`openspec/changes/`。以下为与当前产品演进最相关的变更。

## 1. 演进关系

```
desktop-monolith          一键启动：Tauri spawn 本地 cloud + HTTP sidecar
        │
        ▼
desktop-embedded-runtime  产品壳 + IPC（desktop-host），弱化「多进程手动起服务」心智
        │
        ├── macos-computer-use           原生桌面自动化（基本完成）
        └── trajectory-skill-distillation  轨迹 → Route Skill 提案（基本完成）
```

---

## 2. `desktop-monolith`

- **动机**：开发需开多个终端（cloud / sidecar / UI）
- **做法**：Tauri 父进程自动 spawn；RuntimeGate 等健康检查
- **Release**：不 spawn 本地 cloud；烘焙远程 `VITE_CLOUD_URL`
- **状态**：核心实现完成；部分验证项未勾完
- **文档**：`client/README.md`

---

## 3. `desktop-embedded-runtime`

- **动机**：桌面仍像「Web + Python sidecar」，不够产品化
- **阶段**：4A 产品壳 → 4B 命令 IPC → 4C 可选单进程（PyO3）
- **能力**：`embedded-runtime-ipc`、`desktop-product-shell`
- **状态**：4A 基本完成；4B 部分完成（health/session IPC；run 流与移除 HTTP 仍在推进）
- **影响路径**：`client/src-tauri/`、`backend/app/worker/desktop_*.py`、`frontend/src/client/`

---

## 4. `macos-computer-use`

- **能力**：`desktop-computer-use`、`desktop-app-authorization`、`desktop-perception`、`desktop-action-primitives`
- **实现**：`services/desktop_computer_use/`、`agents/desktop.py`、workflow `desktop_*` 节点
- **状态**：tasks 基本全部完成
- **详见**：[07 · 桌面 Computer Use](./07-desktop-computer-use.md)

---

## 5. `trajectory-skill-distillation`

- **管线**：atomize → classify → distill → 人工 adopt
- **API**：recordings distill、route-skill-proposals、route-skills/buckets
- **UI**：Recording 详情提案面板；Settings → Route Skills
- **状态**：tasks 全部完成
- **详见**：[04 · 执行流 §5](./04-execution-flows.md)

---

## 6. 其他重要已归档/已存在变更（索引）

仓库中还有大量历史 OpenSpec（节选）：

| Change | 主题 |
|--------|------|
| `auto-agent-mvp` / `auto-agent-platform` | 早期 MVP → 平台化 |
| `local-runtime-worker` / `desktop-app` | Worker 与桌面壳 |
| `autonomous-task-mode` | 自主任务 |
| `record-and-generate` | 录制生成工作流 |
| `multi-user-orgs` / `public-api-and-auth` | 多租户与公开 API |
| `sdk-and-mcp` | SDK/MCP |
| `self-healing-selectors` / `selector-cache-learning` | 选择器自愈 |
| `triggers-and-scheduling` / `polling-and-app-triggers` | 触发器 |
| `human-in-the-loop` | 审批节点 |
| `run-artifacts-observability` / `run-cost-tracking` | 可观测与成本 |
| `captcha-antibot-proxy` | 验证码与反爬 |

完整列表见 `openspec/changes/` 目录。

---

## 7. 脚本与验证入口

| 类别 | 示例 |
|------|------|
| Smoke | `scripts/ws_smoke.py`, `platform_smoke.py`, `planner_smoke.py` |
| E2E | `scripts/e2e_platform.py`, `e2e_desktop_host.py` |
| 后端测试 | `backend/tests/test_*.py`（含 desktop / workers / distillation） |

默认端口约定：多数脚本 `AUTO_AGENT_PORT=8001`。

---

## 文档索引

返回：[技术文档首页](../README.md)
