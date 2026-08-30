# 03 · 数据模型

源文件：`backend/app/db/models.py`（SQLModel）。默认库：SQLite（`settings.database_url`）。

## 1. 实体总览

| 域 | 实体 |
|----|------|
| 工作流 | `Workflow`, `WorkflowVersion`, `ChatSession`, `ChatMessage`, `WorkflowCredential` |
| 执行 | `Run`, `RunEvent`, `RunApproval`, `RunArtifact` |
| 调度 | `Trigger`, `ProcessedEvent` |
| 浏览器 | `ProxyConfig`, `BrowserProfile`, `BrowserSession` |
| 技能 | `RouteSkill`, `RouteSkillProposal` |
| 多租户 | `Organization`, `User`, `UserIdentity`, `OrgMembership`, `OAuthDomainRule`, `ApiKey` |
| Worker | `Worker`, `WorkerSession` |
| 其他 | `Credential`, `LlmConfig`, `SelectorCache`, `WebhookSubscription`, `WebhookDelivery`, `Recording` |

启动时通过 `db/migrations.py` 的 `ensure_*` 做增量列/表迁移（非 Alembic）。

---

## 2. 工作流域

### Workflow / WorkflowVersion

- `Workflow`：元数据（`name`, `status`, `org_id`, `visibility`, `current_version_id`）
- `WorkflowVersion`：**不可变**快照（`nodes_json`, `edges_json`, `start_id`, `parameters_json`）
- 编辑产生新版本；Run 始终绑定具体 `workflow_version_id`

### ChatSession / ChatMessage

工作流画布旁的 AI 辅助编辑对话上下文。

### WorkflowCredential

工作流 ↔ 凭证多对多；限制 Run 时可用的 `{{cred.*}}` 范围。

---

## 3. 执行域

### Run（核心字段）

| 字段 | 含义 |
|------|------|
| `status` | `queued` / `running` / `succeeded` / `failed` / `cancelled` / `awaiting_approval` … |
| `mode` | `graph`（工作流图）或 `autonomous`（自主任务） |
| `execution_mode` | `cloud` 或 `worker` |
| `workflow_id` + `workflow_version_id` | 绑定版本 |
| `objective`, `start_url`, `max_steps`, … | 自主任务专用（graph 时多为 null） |
| `worker_id`, `worker_pool` | Worker 分派 |
| `browser_profile_id`, `browser_session_id`, `proxy_id` | 浏览器上下文 |
| `total_*_tokens`, `estimated_cost_usd` | 成本追踪 |
| `parent_run_id` | 子 Run（foreach / subworkflow） |
| `trigger_id` | 触发来源 |

### RunEvent

有序事件：`seq` + `payload_json`。前端/WS/SSE 均消费此流。

典型事件类型：`node_started` / `node_progress` / `node_completed` / `node_failed` / `run_completed` / `run_failed` / 自主步骤事件等。

### RunApproval / RunArtifact

- 审批挂起（人机确认节点）
- 截图、HAR、视频、trace 等产物元数据

---

## 4. 多租户与认证

```
Organization ──< OrgMembership >── User
                    │
              UserIdentity (OAuth provider links)
              OAuthDomainRule (自动开通域)
              ApiKey (org 级公开 API)
```

角色大致：viewer → member → admin → owner（见 `auth/authorization.py`）。平台管理员：`User.platform_admin`。

---

## 5. Worker

| 实体 | 说明 |
|------|------|
| `Worker` | 设备注册：`machine_id`, `org_id`, `approval_status`, capabilities |
| `WorkerSession` | 会话 token；心跳与 TTL |

审批状态：`pending` / `approved` / `rejected`。未批准设备不能启动本地 Run 或接收云端分派。

---

## 6. 浏览器与代理

| 实体 | 说明 |
|------|------|
| `BrowserProfile` | 持久化 profile（含 antibot 相关列） |
| `BrowserSession` | 可复用 live 会话 |
| `ProxyConfig` | 代理配置 |

控制面模式下，云端禁止创建/使用边缘 browser session（policy 拦截）。

---

## 7. Route Skill 与录制

| 实体 | 说明 |
|------|------|
| `Recording` | 浏览器操作录制会话 |
| `RouteSkill` | 已采纳技能（pattern、capability、prompt、tools 约束） |
| `RouteSkillProposal` | 蒸馏产出的待审提案（pending → adopt/dismiss） |

蒸馏管线见 [04 · 执行流](./04-execution-flows.md) 与 [10 · 路线图](./10-roadmap.md)。

---

## 8. 触发与 Webhook

| 实体 | 说明 |
|------|------|
| `Trigger` | cron / webhook / poll / app 触发 |
| `ProcessedEvent` | 幂等去重 |
| `WebhookSubscription` / `WebhookDelivery` | 出站事件投递与重试 |

---

## 9. 凭证与加密

- `Credential`：密文字段；密钥由 `db/crypto.py` Fernet 管理（数据目录下）
- 插值语法：`{{cred.name.field}}`（及 backend 挂载前缀）
- 可选 backend：`local` / `env` / `vault` / HTTP vault

---

## 10. 关系示意

```
Organization
    ├── Workflow ──< WorkflowVersion
    │       └── Run ──< RunEvent
    │             ├── RunApproval
    │             └── RunArtifact
    ├── Worker ──< WorkerSession
    ├── Credential ──< WorkflowCredential
    ├── Recording → RouteSkillProposal → RouteSkill
    └── Trigger → Run
```

下一章：[04 · 执行流](./04-execution-flows.md)
