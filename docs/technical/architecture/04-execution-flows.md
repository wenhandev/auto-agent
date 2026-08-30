# 04 · 执行流

本章描述端到端执行路径：工作流图、自主任务、Worker 分发、轨迹蒸馏。

## 1. 工作流 Run（graph mode）

```
客户端 POST /api/runs
        │
        ▼
  services.runs.enqueue_run
        │
        ▼
  dispatcher（并发上限 / 队列深度）
        │
        ├─ execution_mode=cloud
        │     → runtime_engine.execute_run
        │     → exec/scheduler（DAG） + executor（节点语义）
        │     → Playwright / vision / desktop 节点
        │
        └─ execution_mode=worker
              → worker_hub.try_assign_run
              → WSS 发送 execute 帧
              → WorkerRuntime 本地执行并回传 run_event
```

### DAG 调度要点（`exec/scheduler.py`）

- Indegree 就绪队列
- `condition` / `switch` 按边谓词选择下游
- `merge` 汇合；`foreach` / `subworkflow` 可产生子 Run
- 节点级 `retry`、`on_error`（fail_run / continue / branch）

### 节点语义要点（`executor.py`）

- 确定性动作：`navigate`, `click`, `fill`, `wait`, `extract` …
- 感知节点：`fuzzy_action`, `vision_*`
- 桌面节点：`desktop_open/act/navigate/extract`
- 控制流与数据流：`condition`, `set`, `filter`, `http_request`, `integration` …
- 人机：`approval`, `login`（凭证填充）
- 自愈：selector cache + self-heal（失败时重感知）

---

## 2. 自主任务（autonomous mode）

```
POST /api/tasks  →  services.tasks.create_task
        │
        ▼
  Run(mode=autonomous, objective=…)
        │
        ├─ cloud: _task_queue → agents.autonomous.run_task
        └─ worker: schedule_worker_run → Worker 侧 _handle_autonomous_execute
```

循环内：

1. **Perceive** — 页面/桌面观测（`perception` / `desktop_perception`）
2. **Route Skill** — `match_route_skills` 注入 prompt / 收窄 tools
3. **Decide** — LLM（`autonomous_llm`）选择工具
4. **Act** — 执行工具（浏览器或桌面）
5. **Guardrails** — 域白名单、预算、确认门、无进度检测

结束写入 `Run.result_json` 与 `TaskResult` 结构（见 `schemas_tasks.py`）。

---

## 3. Worker 分发协议

### 连接

- Worker：`WSS /api/v1/workers/connect`（Worker Session Token）
- Hub：`services/worker_hub.py` 维护连接池

### 消息方向（概念）

| 方向 | 类型 | 说明 |
|------|------|------|
| Cloud → Worker | `execute` | 下发 Run（graph 或 autonomous payload） |
| Cloud → Worker | `abort` | 协作中止 |
| Worker → Cloud | `run_event` | 事件帧（含 seq） |
| Worker → Cloud | `artifact_upload` | 产物回传 |
| Worker → Cloud | heartbeat | 保活 |

分派条件：同 org、pool 匹配、`approval_status=approved`、能力（如 headed）满足。

---

## 4. 本地 Desktop Runtime Run

不经过云端 dispatcher 的本地路径：

```
Desktop UI → runtimeBridge → Sidecar POST /runs
        → 本地执行（apply_local_config LLM）
        → SSE /runs/{id}/events + WS /ws/stream/{id}
        → run_id 形如 local_*
```

云端工作流可通过 sidecar `GET /cloud/workflows` 代理拉取；本地 Draft 存 `~/.auto-agent-worker/drafts/`。

离线 Publish：返回 `202` 并写入 `publish_queue.json`，上线后重试。

---

## 5. 录制 → 合成 / 蒸馏

```
Recording session（浏览器动作流）
        │
        ├─ synthesize（synthesizer.py，规则）→ Workflow draft
        └─ distill（distiller + trajectory_distillation）
              → atomize_events（按 URL 分段）
              → classify_capability
              → distill_segment_prompt
              → RouteSkillProposal(pending)
                    │
                    ├─ adopt → RouteSkill（默认可 disabled）
                    └─ dismiss
```

API 入口示例：

- `POST /api/recordings/{id}/distill`
- `POST /api/tasks/{run_id}/distill-route-skills`
- `/api/route-skill-proposals`（list / adopt / dismiss）

运行时：自主 Agent 通过 `match_route_skills` 命中后注入。

---

## 6. 触发器驱动

```
Trigger (cron | webhook | poll | app)
    → enqueue_run(source=trigger, trigger_id=…)
    → 与手动 Run 同一 dispatcher
```

幂等：`ProcessedEvent` 避免重复消费。

---

## 7. 事件与可观测性

```
executor / autonomous / worker
    → run_svc.append_event(seq++)
    → DB RunEvent
    → 内存 fanout（WS 订阅者）
    → 前端 applyEvent / RunLog / 画布高亮
```

直播：`/ws/stream/{run_id}`（CDP screencast JPEG）；桌面本地经 Rust 中继为 Tauri events。

成本：`cost_tracking` 聚合 token / vision 调用到 Run 字段。

---

## 8. 控制面策略影响

当 `execution_backend=control_plane_only`：

- 禁止云端直接 Playwright
- Run 强制走 worker（或拒绝）
- 部分边缘 API（录制、browser session、部分凭证路径）被 `control_plane_policy` 拒绝

详见 `backend/app/services/control_plane_policy.py` 与测试 `tests/test_control_plane_policy.py`。

下一章：[05 · 前端与桌面](./05-frontend-desktop.md)
