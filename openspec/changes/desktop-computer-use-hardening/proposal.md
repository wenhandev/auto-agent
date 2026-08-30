## Why

`macos-computer-use` 已交付协议、FakeBackend、授权与节点/工具骨架，但生产闭环仍有静默缺口：backend 每次 `resolve` 新建导致元素索引跨 tool 失效、Autonomous 观察仍绑浏览器页、Workflow `DesktopAgent` 未接 LLM、嵌入式 Tauri IPC 未映射 Computer Use 设置。现在收口这些债，才能让「看一眼再点」的桌面自动化在真实路径上可靠。

## What Changes

- 进程/会话级复用 `DesktopComputerUseBackend`，保证 `get_app_state` 返回的 index 在同 backend 下次 capture 前对后续 tool 有效
- Autonomous 桌面模式：观察源切到桌面 state；按任务/平台拆分默认工具集；桌面动作后避免无效 browser `perceive`
- Guardrails 按桌面 target 判定破坏性操作，不再误用浏览器 `observation.elements[idx]`
- Workflow `DesktopAgent` 生产路径注入 LLM decide；无 LLM 时的 navigate「一步成功」仅限测试/启发式
- Tauri embedded runtime IPC 补齐 `settings/computer-use` get/put（与 daemon HTTP 对齐）
- `desktop_computer_use_available()` 探测真实依赖（pyobjc / pywinauto），而非仅看 platform
- 热路径：hold 期间缓存 app 解析、减少重复 activate；截图/打字可做按需优化
- 产品面：workflow 插入面板暴露 `desktop_*` 节点；文档/命名厘清 Playwright `computer_use_enabled` vs 原生桌面栈
- Windows：frontmost / 窗口身份 / 危险 `shell=True` 等 parity 修复（不扩 Linux）

## Capabilities

### New Capabilities

- `desktop-backend-lifecycle`: backend 会话复用、可用性探测、hold 期缓存与平台 parity 约束
- `desktop-closed-loop`: Autonomous 桌面观察闭环、工具面拆分、桌面感知 guardrails、Workflow LLM decide
- `desktop-client-parity`: Computer Use 设置 IPC/HTTP 对齐、节点插入面、配置命名澄清

### Modified Capabilities

- （`openspec/specs/` 尚未归档 `macos-computer-use` 能力；本次以新 capability 增量约束生产行为，不直接改归档主线 spec）

## Impact

- `backend/app/services/desktop_computer_use/`（`factory.py`, `macos.py`, `windows.py`, `auth.py`）
- `backend/app/agents/desktop.py`, `autonomous.py`, `autonomous_guardrails.py`, `executor.py`
- `backend/app/schemas_tasks.py`, `backend/app/worker/desktop_protocol.py`, `desktop_api.py`
- `client/src-tauri/src/runtime_host.rs`（IPC mapping）
- `frontend/src/client/` settings + workflow insert palette
- 测试：`test_desktop_*` 需覆盖「非注入路径下跨 tool 索引」与 IPC/available 探测
- 文档：`docs/technical/architecture/07-desktop-computer-use.md` 同步生产行为
