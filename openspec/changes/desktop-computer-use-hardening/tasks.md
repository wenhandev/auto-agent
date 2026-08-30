## 1. Backend lifecycle

- [x] 1.1 实现 `factory.resolve_desktop_backend` 进程级懒单例（注入 Fake 仍优先），并提供测试用 reset
- [x] 1.2 新增测试：无注入路径下 `get_app_state` → index click/type 复用同一实例且索引有效（可用 spy/计数器或 Fake 之外的薄包装验证缓存）
- [x] 1.3 修正 `desktop_computer_use_available()`：探测 extras/构造能力；settings/status 返回可选 `reason`
- [x] 1.4 Windows：修正 frontmost/窗口身份；移除 `open_app` 的 `shell=True` 回退；补失败路径测试

## 2. Client settings parity

- [x] 2.1 `desktop_protocol` 增加 computer-use get/put method 定义，复用 `desktop_api` handler
- [x] 2.2 `runtime_host.rs` 映射 `GET/PUT settings/computer-use` → IPC methods
- [x] 2.3 验证桌面客户端 Settings 经 `runtimeFetch("/settings/computer-use")` 可读可写 Always-allow

## 3. Autonomous closed loop

- [x] 3.1 默认 `allowed_tools` 拆分：浏览器任务不含完整 `DESKTOP_TOOLS`；桌面/显式配置可启用
- [x] 3.2 Autonomous 主循环：桌面上下文下 observe 使用 desktop state；浏览器 web 任务保持 `perceive(page)`
- [x] 3.3 Guardrails：`desktop_click` 等按桌面 target 判定，禁止误用浏览器 `elements[idx]`
- [x] 3.4 Autonomous 桌面 tool 使用 run 级稳定 `holder_id`（或等效）避免每 tool 新 UUID
- [x] 3.5 补充/更新 `test_desktop_autonomous_tools` 与 guardrails 相关测试

## 4. Workflow DesktopAgent production path

- [x] 4.1 `executor` 在有 runtime LLM 时为 `DesktopAgent` 注入 LLM `decide`
- [x] 4.2 收紧无 LLM 生产路径：`run_navigate` 不得因启发式第一步成功而 `completed: true`；测试保留显式短路径
- [x] 4.3 更新 `test_desktop_agent` / `test_desktop_nodes` 期望

## 5. Authoring UI & docs

- [x] 5.1 workflow 插入面板加入 `desktop_open` / `desktop_act` / `desktop_navigate` / `desktop_extract`
- [x] 5.2 更新 `docs/technical/architecture/07-desktop-computer-use.md`：单例、闭环、IPC、双栈命名
- [x] 5.3 Settings/文案区分 Playwright `computer_use_enabled` 与原生桌面栈

## 6. Hot path (follow-on within change)

- [x] 6.1 hold 同一 app 期间缓存 app 解析、减少重复 activate（macOS/Windows）
- [x] 6.2 可选：截图降采样供 LLM、macOS 批量文本输入；有测试或基准说明即可
