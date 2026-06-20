# Sidecar runtime build (for Auto Agent Client)

This folder contains **PyInstaller build scripts** that package the Python runtime (`backend/app/worker/`) into a standalone binary. That binary is **not** a separate user product — it is embedded inside **Auto Agent Client** as the sidecar (`auto-agent-runtime-{target-triple}`).

End users install only the Client from the cloud console (**Settings → 下载客户端** or `/client`). They do not run `auto-agent-worker` from the command line.

## Build output

Build on the **same OS** you target (PyInstaller cannot cross-compile).

| Platform | Script | Output (intermediate) |
|----------|--------|---------------------|
| Windows | `.\worker\build-exe.ps1` | `backend\dist\auto-agent-worker\auto-agent-worker.exe` |
| macOS | `./worker/build-macos.sh` | `backend/dist/auto-agent-worker/auto-agent-worker` |
| Linux | `./worker/build-linux.sh` | `backend/dist/auto-agent-worker/auto-agent-worker` |

Copy/rename into the Tauri bundle (or run the staging helper):

```bash
./worker/stage-client-sidecar.sh   # → client/src-tauri/binaries/runtime-{triple}/
```

See [client/README.md](../client/README.md) for the full release checklist and GitHub Actions workflows.

## CI

- **Build client** (`.github/workflows/build-client.yml`) — builds sidecar + Tauri installers on every relevant push.
- **Release client** (`.github/workflows/release-client.yml`) — publishes installers to GitHub Releases on tag `client-v*`.
- **Build sidecar** (`.github/workflows/build-sidecar.yml`) — sidecar binary only (debugging).

## Developer-only CLI

The same PyInstaller bundle exposes `auto-agent-worker` for **local debugging** (no Tauri UI). Not documented for production users.

```bash
cd backend && source .venv/bin/activate
pip install -e ".[worker-build]"
playwright install chromium

auto-agent-worker doctor --cloud-url https://rpa.wenhandev.com
auto-agent-worker login --cloud-url https://rpa.wenhandev.com
auto-agent-worker serve   # sidecar HTTP on 127.0.0.1:3921
```

Runtime data directory (shared with Client sidecar): `~/.auto-agent-worker/`.
