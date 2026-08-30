# 05 · 前端与桌面客户端

## 1. 总体：单一代码库、双入口

`frontend/src` 是**唯一** React 源码树；`client/` 是 Tauri 2 壳，通过 Vite alias `@` → `../frontend/src` 引用。

```
frontend/src/
├── main.tsx / App.tsx          # Web 入口与路由
├── client/                     # Desktop 专用层
│   ├── main.tsx / App.tsx
│   ├── DesktopShell.tsx
│   ├── api.ts / runtimeBridge.ts
│   └── pages/…
├── pages/                      # Web 页面（部分被 Desktop 复用）
├── components/                 # 共享组件
├── shell/AppShell.tsx          # Web 壳
├── api-platform.ts             # 云端 REST
└── i18n/                       # en / zh-CN / zh-TW

client/
├── src/main.tsx                # import "@/client/main"
├── vite.config.ts              # alias + port 1420
└── src-tauri/                  # Rust 宿主
```

### 产品分工

| | Web | Desktop |
|--|-----|---------|
| 定位 | 查看、运行、组织管理 | 创作、本地执行、凭证、Computer Use |
| 认证 | Cookie 会话 | `workerSessionToken` + `webSessionToken` |
| 策略 | `webPlatformPolicy` 隐藏录制/凭证等 | 完整功能 |
| Runtime | 无 | 嵌入式 Python sidecar |

---

## 2. Web 路由（`App.tsx` + `routes.ts`）

| 路径 | 页面 |
|------|------|
| `/login`, `/login/oauth/callback` | 登录 / OAuth |
| `/client` | 客户端下载 |
| `/workflows`, `/workflows/:id` | 工作流列表 / 详情 |
| `/runs`, `/runs/:runId` | 历史 / 回放 |
| `/tasks` | 自主任务 |
| `/settings`, `/settings/members` | 设置 / 成员 |
| `/admin/:section` | 平台管理 |
| `/recordings`, `/credentials`, `/browser-*` | 按 policy 或 `DesktopOnlyFeaturePage` |

壳：`AppShell`（可折叠侧边栏 + Outlet）。

---

## 3. Desktop 路由（`client/App.tsx`）

启动链：`RuntimeStatusProvider` → `DesktopStartupGate` → `DesktopAuthProvider` → 路由。

| 路径 | 页面 |
|------|------|
| `/login`, `/login/oauth/callback` | 桌面登录 / OAuth |
| `/pending` | Worker 待审批 |
| `/` | `HomePage` 仪表盘 |
| `/device` | 设备预检 |
| `/runs`, `/runs/console`, `/runs/:runId` | 历史 / **本地控制台** / 回放路由 |
| `/workflows`, `/drafts/:id` | 云端 + 本地草稿 |
| `/recordings/*`, `/tasks/new` | 复用 Web 页面 |
| `/settings` | 本地 LLM / 设备 |

`RunReplayRouter`：`runId` 以 `local_` 开头 → `LocalRunReplayPage`；否则云端 `RunReplayPage`。

壳：`DesktopShell`（Runtime 状态点、Tauri overlay title bar、Cloud 功能分区）。

---

## 4. API 层

```
Web Pages ──► api-platform.ts (Cookie) ──► Cloud /api/*
Desktop ──┬─► api-platform (Bearer via configureCloudApi)
          ├─► client/api.ts (Worker login / cloud proxy)
          └─► runtimeBridge ──► Tauri invoke ──► Runtime
```

| 模块 | 作用 |
|------|------|
| `api-platform.ts` | 完整云端 `apiClient`；可注入 Bearer + baseUrl |
| `client/api.ts` | 双通道：Cloud fetch + Runtime fetch；登录后 `scheduleRuntimeSync` |
| `runtimeBridge.ts` | `runtime_invoke` / SSE·WS 订阅（Tauri events） |
| `cloudApi.ts` | 登录后注入 token |

---

## 5. Tauri / Rust 宿主

路径：`client/src-tauri/src/`

| 文件 | 职责 |
|------|------|
| `lib.rs` | 启动：spawn cloud/runtime、托盘、注册 commands |
| `runtime_bridge.rs` | Dev: TCP `:3921`；Release: Unix socket IPC；SSE/WS 中继 |
| `runtime_host.rs` | HTTP 路径 ↔ IPC 方法映射 |
| `runtime_protocol.rs` | 4-byte length + UTF-8 JSON 帧（v=1） |
| `oauth_callback.rs` | `127.0.0.1:8745` 捕获 OAuth code → emit `oauth-callback` |

### 启动模式

| 模式 | Cloud | Runtime |
|------|-------|---------|
| Debug | spawn uvicorn `:8001` | spawn `python -m app.worker.daemon` `:3921` |
| Release | 不 spawn（用 `VITE_CLOUD_URL`） | bundled `auto-agent-runtime` + `desktop-host` IPC |

关闭窗口 → hide 到托盘；Quit 杀死子进程。

---

## 6. 关键流程

### Desktop 登录

1. 并行：`POST /api/v1/workers/login` + `POST /api/auth/login`（或 OAuth exchange）
2. 保存 `DesktopSession` 到 localStorage
3. `configureCloudApi` + `POST /session` 同步到 Runtime
4. `pending` → 等待审批；否则进入 `DesktopShell`

OAuth：系统浏览器 → 云端 → 回调 Rust `:8745` → WebView 导航完成交换。

### Run Console 本地运行

1. 拉取云端工作流列表
2. `POST /runs`（经 Runtime）→ `local_*` id
3. `subscribeRunEvents` + `subscribeStreamFrames`
4. Abort → `POST /runs/{id}/abort`

---

## 7. 状态与 i18n

| Store / Context | 用途 |
|-----------------|------|
| `store.ts` | 画布节点态、回放日志 |
| `platformStore.ts` | 平台 Run / WS |
| React Query | Web `me`、列表缓存 |
| `DesktopAuthContext` / `RuntimeStatusContext` | 会话与就绪 |

语言：`en` / `zh-CN` / `zh-TW`（`auto-agent-language`）。

类型：`types.ts`（DSL）、`types-platform.ts`（REST DTO）、`client/types.ts`（DesktopSession 等）。

---

## 8. 开发命令

| 命令 | 说明 |
|------|------|
| `frontend/` `npm run dev` | Web，:5173，代理 `/api` |
| `client/` `npm run tauri:dev` | Desktop，:1420，自动 spawn 服务 |
| `VITE_CLOUD_URL` | 生产包烘焙云端 URL |

下一章：[06 · Worker 与 Runtime](./06-worker-runtime.md)
