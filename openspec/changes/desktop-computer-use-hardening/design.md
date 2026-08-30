## Context

原生桌面 Computer Use（`openspec/changes/macos-computer-use/`）已有 Protocol / Fake / macOS AX / Windows UIA、授权、app lock、Autonomous 工具与 `desktop_*` 节点。文档见 `docs/technical/architecture/07-desktop-computer-use.md`。

当前生产路径缺口（已对照代码确认）：

1. `resolve_desktop_backend()` 每次 `new` 实例 → `_last_elements` 跨 autonomous tool 丢失（测试注入单例掩盖了问题）。
2. Autonomous 主循环固定 `perceive(page)`；桌面 tool 后仍观察浏览器。
3. `executor` 构造 `DesktopAgent` 无 `decide=`；无 LLM 时 `run_navigate` 第 0 步成功即返回。
4. daemon 有 `/settings/computer-use`，Tauri `runtime_host` 仅映射 `settings.llm.*`。
5. Guardrails 对 `desktop_click` 查浏览器 elements；`available()` 只看 platform。

约束：不引入 Linux；不改 Playwright `computer_use_enabled` 语义；保持 FakeBackend + `set_desktop_backend_for_tests` 测试面。

## Goals / Non-Goals

**Goals:**

- 索引动作在真实 `resolve` 路径上可靠
- 桌面任务闭环：观察 → 决策 → 动作 → 再观察（桌面 state）
- Workflow 生产路径可用 LLM decide
- 嵌入式客户端可读写 Computer Use 授权设置
- 可用性探测与命名不误导用户

**Non-Goals:**

- 跨进程分布式 app lock / 多机桌面编排
- Allow-once 完整产品弹窗（可留桩；本次至少不假装已有）
- 背景虚拟光标 / Locked 模式
- 轨迹蒸馏合成 `desktop_*` 节点（可后续 change）
- 大规模 Windows UI 质量重写（只修明确 parity bug）

## Decisions

### 1. Backend 生命周期：进程级懒单例 + 可重置

**选择：** `factory` 缓存已解析的真实 backend（darwin/win32 各一），`set_desktop_backend_for_tests` 仍优先；提供 `reset_desktop_backend_for_tests()` / 进程内 reset 供测试与异常恢复。

**替代：**

- 每 run 新建 backend：仍需把 index→bounds 序列化进 tool 结果，改动面更大。
- 稳定 `ax_ref` 字符串：更优长期方案，但 v1 用单例即可满足现有 index 契约（原 spec：index 在同 instance 下次 capture 前有效）。

**理由：** 最小改动对齐已有契约；测试路径不变。

### 2. Autonomous 桌面闭环：模式标志 + 条件感知

**选择：** 当最近一次成功桌面 tool 持有 `app`，或任务 `allowed_tools` 仅含桌面/显式 `runtime=desktop` 时，主循环用 `get_app_state` → `observation_from_desktop_state`（或现有 compact 映射）替代 `perceive(page)`。默认工具集：浏览器任务不含 `DESKTOP_TOOLS`；桌面/混合任务显式加入。

**替代：** 永远双感知（浏览器+桌面）— token/延迟不可接受。

**理由：** 决策与真实 UI 对齐，并降噪 tool schema。

### 3. Guardrails：按 tool 命名空间分支

**选择：** `desktop_click` / `desktop_type` 使用桌面 observation（或 tool args 中的 `app` + index 对应 name/role）；缺桌面 observation 时对坐标点击视为高风险，对纯 app 名检查保持保守。

**替代：** 坐标一律 require_confirmation — 过严会卡死自动化；本次先修「错 observation」假安全感。

### 4. Workflow LLM decide：复用 autonomous 桌面 decide 适配器

**选择：** `executor` 在配置了 runtime LLM 时注入 `DesktopDecideFn`（包装现有 vision/desktop prompt 路径）；无 LLM 时保留启发式，且 **仅测试** 允许 navigate 早退（或用 env/`settings` 显式 flag）。生产无 LLM：navigate 跑满启发式步数或明确失败，而不是「一步成功」。

### 5. Client parity：IPC 镜像 HTTP

**选择：** `desktop_protocol` + `runtime_host.rs` 增加 `settings.computer_use.get/put`，语义同 `desktop_api`；UI 继续 `runtimeFetch("/settings/computer-use")`，由 mapping 转发。

**替代：** UI 直打 daemon HTTP — 与 embedded-runtime 方向冲突。

### 6. Availability：构造探测

**选择：** `desktop_computer_use_available()` 尝试 import/轻量 probe（不强制完整 AX 权限检查）；失败则 false，并在 settings API 返回 `reason`。

### 7. 热路径（第二阶段可并行）

Hold 同一 `app` 期间：缓存 `list_apps` 解析结果；连续 action 跳过重复 `activate`（除非 frontmost 丢失）；PNG 可降采样后再入 LLM（全分辨率仍可作 artifact）。打字批量输入作为 macOS 跟进项。

### 8. 命名澄清（文档 + API 字段注释）

Settings / docs 明确：`computer_use_enabled` = Playwright 坐标 fallback；原生栈 = platform backend + app allowlist。可选 API 字段别名 `desktop_native_available`，不做 **BREAKING** 重命名。

## Risks / Trade-offs

- [进程单例持有 OS 资源] → Mitigation：reset API；异常后重建；测试 teardown 清空
- [桌面模式误判导致跳过 browser perceive] → Mitigation：仅在明确桌面上下文切换；混合任务保留 browser 优先（原 routing 要求）
- [IPC 与 daemon 双路径漂移] → Mitigation：handler 共用 `desktop_api` 函数，mapping 仅做路由
- [无 LLM navigate 行为变更] → Mitigation：测试更新期望；文档注明启发式不再伪成功
- [Windows shell=True 移除后 open 失败率] → Mitigation：保留受控启动路径列表，失败返回明确错误

## Migration Plan

1. 先合并 factory 单例 + 跨 tool 索引测试（无 UI 依赖）
2. IPC mapping + available 探测（解锁客户端授权）
3. Autonomous 闭环 + 默认工具集 + guardrails
4. Workflow LLM decide + navigate 早退收紧
5. 热路径与 Windows parity
6. 更新 `07-desktop-computer-use.md`

回滚：单例可 env 关闭回退到每调用 new（仅应急）；IPC 缺失时 UI 仍可走 daemon HTTP（dev）。

## Open Questions

- Allow-once 是否在本 change 做最小「运行时授权错误码 + Settings 文案」，还是完全留给后续 UX change？
- 桌面模式标志放在 task schema（`runtime: desktop|browser|auto`）还是仅由 allowed_tools 推断？
- macOS TCC「必须从 .app 进程发起」是否已阻塞真实输入？若是，是否需要把 click/type 桥到 Tauri（本 change 仅记录 spike）？
