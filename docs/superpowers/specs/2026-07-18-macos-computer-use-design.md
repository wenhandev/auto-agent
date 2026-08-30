# Desktop Computer Use 设计（macOS + Windows）

日期：2026-07-18  
状态：已实现（P0–P2 骨架；后台光标未做）  
对标：OpenAI Codex Computer Use（无障碍树优先 + 截屏 + 按 App 授权）

## 目标

在 Auto Agent 中提供完整 Computer Use：Agent 可查看屏幕、点击、打字，操作任意**已授权**的桌面应用（**macOS + Windows**）。入口同时覆盖：

1. **自主任务**：目标可指向原生 App，不限浏览器
2. **工作流节点**：可编排 `desktop_*` 节点

现有浏览器 vision / autonomous（Playwright + `perception.py`）保持不变；桌面能力作为平行后端接入同一 Agent 循环。

## 非目标（v1）

- Linux 桌面自动化
- 后台虚拟光标（Codex 式并行光标）；架构预留，v1 为前台接管
- Locked use（锁屏后继续操作）
- 自动化 Terminal / cmd / PowerShell、Auto Agent 自身、系统安全/UAC/权限弹窗
- 确定性 AX/UIA selector 节点（如手写 `desktop_click` selector）；v1 以目标驱动节点为主
- 单独沙箱浏览器配置文件（Computer Use 使用用户本机 App 状态）

## 已确认产品决策

| 决策 | 选择 |
|------|------|
| 能力范围 | 完整 Computer Use（任意已授权 App） |
| 平台 | macOS + Windows（Linux 不做） |
| 输入占用 | v1 前台接管；抽象层可替换为后台光标 |
| 入口 | 自主任务 + 工作流 `desktop_*` 节点 |
| 权限 | 系统权限（macOS TCC）+ 按 App 首次授权 / Always allow |
| 感知 | 无障碍树优先（macOS AX / Windows UIA）+ 截屏兜底 |

## 架构

```
Desktop App (Tauri)
  · 系统权限引导（Screen Recording / Accessibility）
  · App 首次授权 / Always allow UI
  · 自主任务 + 工作流编辑器
        │ invoke / IPC
        ▼
Local Runtime (Python)
  Autonomous Loop / Graph Executor
        │
        ▼
  Tool surface: browser_* | desktop_*
        │
        ▼
  DesktopComputerUseBackend（协议）
    get_app_state / click / type / scroll / list_apps …
    v1: ForegroundInputDriver
    later: BackgroundCursorDriver
        │
        ├── 窗口截屏（ScreenCapture）
        ├── AX Tree（AXUIElement）
        └── 合成输入（v1 前台 CGEvent / AX 动作）
```

### 组件职责

| 组件 | 职责 |
|------|------|
| `desktop_perception` | 对标 `perception.py`：窗口截屏 + AX 索引元素图 → `Observation` |
| `DesktopComputerUseBackend` | 平台能力抽象；macOS AX + Windows UIA |
| `ForegroundInputDriver` | 激活目标窗口 + 合成鼠标/键盘（会打断用户） |
| App 授权服务 | 本地持久化 Always allow（bundle id）；未授权则 HITL |
| 工具面 / 节点 | 自主任务调用 `desktop_*`；工作流编排 `desktop_*` 节点 |

### 原生桥接原则

编排逻辑留在 Python（与现有 worker 一致）。若 TCC 要求截屏/注入必须由 `.app` 主进程发起，则 Tauri 提供 thin native bridge，Python 仍握循环与工具分发。

## 工具面

### 自主任务工具

| 工具 | 作用 |
|------|------|
| `list_apps` | 列出前台/已运行 App（bundle id + 名称） |
| `open_app(app)` | 启动或激活（需授权或触发授权） |
| `get_app_state(app)` | 窗口截屏 + AX 索引元素列表（index 仅当轮有效） |
| `desktop_click(app, index)` | 按元素 index 点击；可选坐标兜底 |
| `desktop_type(app, index?, text)` | 聚焦后输入；无 index 则打到当前焦点 |
| `desktop_key(app, key)` | 快捷键 / 特殊键 |
| `desktop_scroll(app, direction, amount?)` | 滚动 |
| `desktop_done(success, summary)` | 结束桌面子目标（或复用现有 `done`） |

### 路由规则

- 目标为浏览器且已有 Playwright 会话 → 优先现有 browser / vision 工具
- 原生 App、无浏览器会话、或用户明确要求操作桌面 → `desktop_*`
- 有结构化集成（未来 plugin/MCP）时优先集成，Computer Use 作 GUI 兜底（对齐 Codex）

### 工作流节点

| 节点 | 参数要点 | 行为 |
|------|----------|------|
| `desktop_open` | `app` | 启动/激活 |
| `desktop_act` | `app`, `instruction` | 单步 observe → 一动作（对标 `vision_act`） |
| `desktop_navigate` | `app`, `goal`, `max_steps?` | 多步循环至目标或步数用尽（对标 `vision_navigate`） |
| `desktop_extract` | `app`, `instruction`, `schema?` | 结构化抽取（对标 `vision_extract`） |

### 事件

每步发射 `desktop_step`：`app`, `step_index`, `thought`, `action`, `target_index`, `screenshot_ref`。与 `vision_step` 平行，Run Console 复用缩略图 + 思路展示。

## 权限、安全与运行约束

### 两层权限

1. **系统权限**：Screen Recording + Accessibility；缺失时引导 System Settings，不静默失败
2. **App 授权**：首次询问 Allow once / Always allow / Deny；Always allow 存本地，Settings → Computer Use 可撤销

### 硬禁止

- Terminal
- Auto Agent 自身
- macOS 系统安全/权限弹窗

### 敏感动作

支付、删除、发送消息、改账号设置等：复用 `require_confirmation` / HITL。

### 运行约束

| 约束 | v1 行为 |
|------|---------|
| 平台 | macOS / Windows 桌面客户端；Web 与 Linux 提示不可用 |
| 输入 | 前台接管（激活窗口、移动系统指针） |
| 并发 | 同一时刻同一 App 仅一个 Computer Use 任务 |
| 锁屏/休眠 | 失败并给出诊断 |
| 浏览器 | 已有 Playwright 会话时优先浏览器工具 |
| 预算 | 复用 autonomous 的 `max_steps` / `max_seconds` |

### 隐私

截屏与 AX 摘要写入本机 run artifacts；上传云端策略与现有 run 同步一致。Always allow 名单仅本地存储。

## 落地模块

| 区域 | 内容 |
|------|------|
| `backend/app/services/desktop_perception.py` | 窗口截屏 + AX → indexed Observation |
| `backend/app/services/desktop_computer_use/` | Backend 协议、ForegroundInputDriver、App 授权存储 |
| `backend/app/agents/` | 桌面工具注册进 autonomous；desktop_navigate 循环 |
| `backend/app/executor` + schema | `desktop_*` 节点类型与分发 |
| `client/src-tauri` | 权限检测/引导；必要时 native bridge |
| `frontend/src/client` | Computer Use 设置、自主任务桌面目标、节点 Inspector、`desktop_step` UI |

## 测试

- 单元：AX → 元素索引；未授权拒绝；禁止列表
- 集成（需本机权限）：TextEdit 等系统 App 上 `get_app_state` → click → type
- 契约：`desktop_step` 事件形状；节点 schema
- 无 macOS CI：mock Backend，覆盖分发与授权逻辑

## 分期

| 阶段 | 交付 |
|------|------|
| P0 | macOS Backend + 权限/白名单 + get_app_state / click / type；自主任务可调桌面工具 |
| P1 | 工作流 `desktop_open` / `act` / `navigate` / `extract` + Run Console |
| P2 | 设置页、引导、敏感 HITL、并发/锁屏诊断打磨 |
| P3 | Windows UIA Foreground driver（`desktop-windows` extras） |
| 以后 | BackgroundCursorDriver（macOS）；Linux 不考虑 |

## 成功标准（v1）

在 macOS 桌面客户端完成系统权限与 App 授权后，用户可用自然语言驱动备忘录（或同类 App）完成「写一段文字并保存」；Run 中可见逐步截图与动作；同一能力可通过 `desktop_navigate` 编入工作流。

## 与现有能力的关系

- **复用**：autonomous 循环、HITL、步数/时间预算、run artifacts、vision 事件展示模式
- **平行**：`desktop_perception` 对标 `perception.py`，不替换浏览器 perception
- **不替换**：Playwright 浏览器自动化仍是 Web 任务的主路径
