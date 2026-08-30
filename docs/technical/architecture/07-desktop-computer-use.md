# 07 · 桌面 Computer Use

将自动化从「仅浏览器」扩展到 **原生桌面应用**（类似 Computer Use / Codex 风格）。  
OpenSpec：`openspec/changes/macos-computer-use/`（初版）+ `openspec/changes/desktop-computer-use-hardening/`（生产闭环加固）。

## 1. 与浏览器自动化的区别

| | Playwright / Browser | Desktop Computer Use |
|--|----------------------|----------------------|
| 目标 | Chromium 页面 | 任意授权桌面 App |
| 感知 | DOM / 截图 / a11y | AX（macOS）/ UIA（Windows）+ 截图 |
| 动作 | click/fill/navigate… | click/type/key/scroll + open_app |
| 配置开关 | 始终可用（控制面策略另计） | 平台后端 + 应用授权 |

注意：`settings.computer_use_enabled` 控制的是 **Playwright 坐标 fallback**（`services/computer_use.py`），与本原生栈不同。桌面客户端 Settings 里的「原生桌面 Computer Use」只管理 app allowlist / 可用性。

---

## 2. 模块地图

```
backend/app/
├── agents/desktop.py                         # observe→act 循环（可注入 LLM decide）
├── services/desktop_perception.py            # 感知摘要 → Observation
└── services/desktop_computer_use/
    ├── protocol.py                           # Backend 协议
    ├── factory.py                            # 进程级单例 resolve_desktop_backend()
    ├── macos.py                              # pyobjc AX + CGEvent
    ├── windows.py                            # pywinauto
    ├── fake.py                               # 测试用 FakeBackend
    ├── auth.py                               # Always-allow / Allow-once
    ├── forbidden.py                          # 禁止目标
    ├── app_lock.py                           # 应用锁
    └── session.py                            # 会话状态
```

可选依赖：`desktop-macos`（pyobjc）、`desktop-windows`（pywinauto/Pillow）。  
`desktop_computer_use_available()` 会探测 extras，不只看 `sys.platform`。

---

## 3. Backend 生命周期

- `resolve_desktop_backend()`：**进程级懒单例**（测试注入 Fake 优先）。
- 元素 index 仅在**同一 backend 实例**、下次 `get_app_state` 之前有效（跨 autonomous tool 必须复用实例）。
- 测试用 `reset_desktop_backend_for_tests()` 清空注入与缓存。

---

## 4. Workflow 节点

| NodeType | 含义 |
|----------|------|
| `desktop_open` | 打开/聚焦应用 |
| `desktop_act` | 执行桌面动作 |
| `desktop_navigate` | 应用内导航类操作 |
| `desktop_extract` | 提取 UI 文本/状态 |

由 `executor.py` 调度：有 runtime LLM 时注入 `llm_desktop_decide`；无 LLM 时用启发式。  
无 LLM 时 `desktop_navigate` **不会**因任意第一步成功而伪完成；仅当动作与目标语义匹配（如 goal 含 “Save” 且点击了 Save）时才 `completed: true`（测试仍可用 `allow_heuristic_short_circuit=True`）。

节点可从工作流插入面板「桌面」分组添加。

---

## 5. 自主工具（Autonomous）

默认浏览器工具集 **不含** `DESKTOP_TOOLS`。桌面任务须显式设置 `TaskSpec.allowed_tools`（可用 `DEFAULT_DESKTOP_ALLOWED_TOOLS` 或自定义混合列表）。自主任务页提供「原生桌面工具」开关，开启后会预填上述工具集（若同时有起始 URL 则与浏览器工具合并）。

典型工具：

- `list_apps` / `open_app` / `get_app_state`
- `desktop_click` / `desktop_type` / `desktop_key` / `desktop_scroll`

桌面上下文（`Memory.active_desktop_app`）下，observe 使用 `observation_from_desktop_state`，而非浏览器 `perceive(page)`。  
同一 run 复用稳定 `desktop_lock_holder`。

---

## 6. 授权与客户端

- **Always-allow** / **Allow-once**（`auth.py`；产品 UI 当前以 Always-allow 为主）
- 禁止列表（`forbidden.py`）
- 应用锁（`app_lock.py`）

设置 API：daemon HTTP `/settings/computer-use`，以及嵌入式 Tauri IPC `settings.computer_use.get/put`（`runtimeFetch` 同源路径）。  
响应含 `available` + 可选 `reason`。

---

## 7. 测试

| 测试文件 | 覆盖 |
|----------|------|
| `test_desktop_computer_use_fake.py` | FakeBackend + factory 单例 / availability |
| `test_desktop_windows_launch.py` | Windows 受控启动（无 shell=True） |
| `test_desktop_computer_use_auth.py` | 授权 |
| `test_desktop_app_lock_and_session.py` | 锁与会话 / guardrails |
| `test_desktop_agent.py` / `test_desktop_autonomous_tools.py` | Agent / 工具 / 桌面观察 |
| `test_desktop_nodes.py` / `test_desktop_protocol.py` / `test_desktop_host.py` | 节点与 IPC |
| `test_desktop_e2e.py` | 端到端 |

设计细节另见：

- `docs/superpowers/specs/2026-07-18-macos-computer-use-design.md`
- `openspec/changes/desktop-computer-use-hardening/`

下一章：[08 · 部署与运维](./08-deploy.md)
