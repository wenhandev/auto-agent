# 06 · Worker 与 Runtime

Worker **不是**独立面向终端用户的产品，而是打包进 **Auto Agent Client** 的 Python 运行时（sidecar）。源码在 `backend/app/worker/`，打包脚本在 `worker/`。

## 1. 角色

| 角色 | 说明 |
|------|------|
| **Cloud Worker** | `auto-agent-worker start`：WSS 连接控制面，执行分派任务 |
| **Desktop Sidecar** | `serve` / `daemon`：本地 HTTP `:3921`（或 UDS）供 Tauri 调用 |
| **desktop-host** | Release IPC：framed JSON over Unix socket + 可选 stream UDS |

数据目录：`~/.auto-agent-worker/`（session、llm.json、drafts、publish_queue）。

---

## 2. CLI（`app.worker.cli`）

| 命令 | 用途 |
|------|------|
| `doctor` | 环境预检（Playwright、权限等） |
| `login` / `logout` | 云端认证 |
| `start` | WSS 接任务 |
| `install-browsers` | Playwright Chromium |
| `serve` | Sidecar HTTP（默认 `127.0.0.1:3921`） |
| `desktop-host` | Release IPC 宿主 |

开发调试：`cd backend && python -m app.worker.daemon`。

---

## 3. Sidecar HTTP API（`daemon`）

仅绑定 loopback。主要端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health`, `/ready`, `/status` | 健康与审批/连接状态 |
| POST/DELETE | `/session` | 同步/清除 Desktop 会话 |
| GET/PUT | `/settings/llm` | 本地 LLM（Fernet 加密） |
| GET | `/cloud/workflows[/{id}]` | 代理云端（用存储的 web token） |
| POST | `/cloud/workflows/{id}/pull` | 拉取为本地 Draft |
| GET/POST | `/drafts`, `…/publish` | 本地草稿；离线 publish → 202+队列 |
| GET/POST | `/runs`, `…/abort` | 本地运行（未批准 → 403） |
| GET | `/runs/{id}/events` | SSE |
| WS | `/ws/stream/{id}` | 直播帧 |

桌面模式使用 **本地 LLM 配置**（`apply_local_config`），不走云端 `install_llm_proxy`。

相关模块：`daemon.py`、`local_runs.py`、`desktop_api.py`、`desktop_host.py`、`desktop_protocol.py`、`desktop_runtime.py`、`preflight.py`、`runtime.py`。

---

## 4. 打包与嵌入

### PyInstaller

- Spec：`worker/auto-agent-worker.spec`（onedir）
- 构建：`worker/build-macos.sh` / `build-linux.sh` / `build-exe.ps1`
- 中间产物：`backend/dist/auto-agent-worker/`
- Extra：`pip install -e ".[worker-build]"`

### Stage 到 Tauri

```bash
./worker/stage-client-sidecar.sh
# → client/src-tauri/binaries/runtime-{triple}/
# 可执行文件名 auto-agent-runtime-{triple}
```

不可交叉编译，需在目标 OS 上构建。

### CI

| Workflow | 作用 |
|----------|------|
| `.github/workflows/build-client.yml` | sidecar + Tauri 安装包 |
| `release-client.yml` | tag `client-v*` → DMG/MSI/AppImage |
| `build-sidecar.yml` | 仅 sidecar 调试产物 |

---

## 5. 与 Tauri 的集成演进

```
Phase 1–3 (desktop-monolith)
  Dev: Tauri spawn uvicorn:8001 + daemon:3921 (HTTP)
  Release: 仅 bundled sidecar + 远程云

Phase 4 (desktop-embedded-runtime)
  产品壳 + 命令 IPC（desktop-host）
  WebView 不直连 localhost；Rust 中继
  目标：移除 release 路径上的 uvicorn 心智模型
```

当前：Dev 仍多用 TCP HTTP；Release 倾向 IPC（见 `runtime_bridge.rs`）。

---

## 6. 预检与设备状态

`preflight` / `/doctor` 检查 Playwright、OS 权限（如 macOS Accessibility）等。  
Desktop UI：`DeviceStatusPage` + `deviceStatus.ts` 展示文案；`RuntimeStatusContext` 轮询就绪。

下一章：[07 · 桌面 Computer Use](./07-desktop-computer-use.md)
