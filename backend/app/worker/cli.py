"""Local runtime worker CLI."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import platform
import socket
import sys
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import websockets

from app.worker import credentials as cred_svc
from app.worker import preflight
from app.worker.runtime import WorkerRuntime


logger = logging.getLogger(__name__)
AGENT_VERSION = "0.1.0"


def _machine_id() -> str:
    saved = cred_svc.load_credentials()
    if saved and saved.get("machine_id"):
        return str(saved["machine_id"])
    mid = str(uuid.uuid4())
    if saved:
        saved["machine_id"] = mid
        cred_svc.CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        cred_svc.CREDENTIALS_FILE.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return mid


def _default_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return platform.node() or "unknown"


def _ws_url(cloud_url: str) -> str:
    parsed = urlparse(cloud_url.rstrip("/"))
    scheme = "wss" if parsed.scheme in ("https", "wss") else "ws"
    if parsed.scheme == "http":
        scheme = "ws"
    host = parsed.netloc or parsed.path
    return f"{scheme}://{host}/api/v1/workers/connect"


def cmd_doctor(args: argparse.Namespace) -> int:
    env = asyncio.run(preflight.run_doctor(args.cloud_url, agent_version=AGENT_VERSION))
    print(json.dumps(env, indent=2, ensure_ascii=False))
    return 1 if env.get("environment_status") == "not_ready" else 0


def cmd_login(args: argparse.Namespace) -> int:
    cloud_url = (args.cloud_url or "").strip().rstrip("/")
    if not cloud_url:
        cloud_url = input("Cloud URL: ").strip().rstrip("/")
    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")

    machine_id = args.machine_id or _machine_id()
    env = asyncio.run(preflight.run_doctor(cloud_url, agent_version=AGENT_VERSION))

    payload = {
        "email": email,
        "password": password,
        "machine_id": machine_id,
        "display_name": args.display_name or _default_hostname(),
        "hostname": _default_hostname(),
        "tags": args.tags or ["default"],
        "agent_version": AGENT_VERSION,
        "environment": env,
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(f"{cloud_url}/api/v1/workers/login", json=payload)
    if res.status_code != 200:
        print(f"login failed: {res.status_code} {res.text}", file=sys.stderr)
        return 1
    data = res.json()
    cred_svc.save_credentials(
        cloud_url=cloud_url,
        worker_session_token=data["worker_session_token"],
        worker_id=data["worker_id"],
        org_id=data["org_id"],
    )
    saved = cred_svc.load_credentials() or {}
    saved["machine_id"] = machine_id
    cred_svc.CREDENTIALS_FILE.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    print(f"logged in worker_id={data['worker_id']}")
    approval = data.get("approval_status", "approved")
    if approval == "pending":
        print(
            "等待管理员授权：请在 Web 设置 → Workers 中请管理员批准此设备。"
            "（Auto Agent Client 登录后会自动连接；开发者可运行 auto-agent-worker start。）",
            file=sys.stderr,
        )
    elif approval == "rejected":
        print("此设备已被拒绝，请联系管理员。", file=sys.stderr)
        return 1
    return 0


def _fetch_worker_status(cloud_url: str, token: str) -> Optional[dict[str, Any]]:
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"{cloud_url}/api/v1/workers/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    if res.status_code != 200:
        return None
    data = res.json()
    return data if isinstance(data, dict) else None


def _wait_for_approval(cloud_url: str, token: str) -> int:
    print(
        "设备尚未授权。请在 Web 设置 → Workers 中请管理员批准此设备。"
        "每 10 秒检查一次状态…",
        file=sys.stderr,
    )
    while True:
        status = _fetch_worker_status(cloud_url, token)
        if status is None:
            print("无法获取授权状态，请重新登录。", file=sys.stderr)
            return 1
        approval = status.get("approval_status", "pending")
        if approval == "approved":
            print("设备已授权，正在连接…")
            return 0
        if approval == "rejected":
            print("此设备已被管理员拒绝。", file=sys.stderr)
            return 1
        try:
            import time

            time.sleep(10)
        except KeyboardInterrupt:
            print("已取消。", file=sys.stderr)
            return 1


def cmd_logout(_args: argparse.Namespace) -> int:
    cred_svc.clear_credentials()
    print("credentials cleared")
    return 0


def cmd_install_browsers(_args: argparse.Namespace) -> int:
    """Download Chromium for Playwright (required once per machine)."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("playwright is not installed", file=sys.stderr)
        return 1
    print("Installing Chromium for Playwright (may take a few minutes)…")
    preflight.install_chromium()
    print("Done. Run: auto-agent-worker doctor")
    return 0


def _frozen_bootstrap() -> None:
    """When running as a PyInstaller bundle, use the exe directory as cwd."""
    browsers_dir = cred_svc.CREDENTIALS_DIR / "browsers"
    browsers_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers_dir))
    if getattr(sys, "frozen", False):
        os.chdir(Path(sys.executable).resolve().parent)


async def _run_worker_loop(cloud_url: str, token: str, env: dict[str, Any]) -> None:
    url = f"{_ws_url(cloud_url)}?token={token}"

    async with websockets.connect(
        url, ping_interval=20, ping_timeout=20, proxy=None
    ) as ws:

        async def send_frame(frame: dict[str, Any]) -> None:
            await ws.send(json.dumps(frame, default=str))

        runtime = WorkerRuntime(
            send=send_frame,
            cloud_url=cloud_url,
            worker_token=token,
        )
        await ws.send(
            json.dumps(
                {
                    "max_concurrent_runs": 1,
                    "tags": ["default"],
                    "environment": env,
                    "agent_version": AGENT_VERSION,
                }
            )
        )

        async def heartbeat_loop() -> None:
            while True:
                await asyncio.sleep(30)
                await ws.send(
                    json.dumps(
                        {
                            "type": "heartbeat",
                            "active_runs": runtime.active_runs,
                            "environment": env,
                        }
                    )
                )

        hb_task = asyncio.create_task(heartbeat_loop())
        try:
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(frame, dict):
                    continue
                frame_type = frame.get("type")
                if frame_type == "execute_run":
                    asyncio.create_task(runtime.handle_execute(frame))
                elif frame_type == "abort":
                    await runtime.handle_abort(frame)
                elif frame_type == "resume_run":
                    await runtime.handle_resume(frame)
                elif frame_type == "stream_subscribe":
                    await runtime.handle_stream_subscribe(frame)
                elif frame_type == "stream_unsubscribe":
                    await runtime.handle_stream_unsubscribe(frame)
                elif frame_type == "artifact_upload_ack":
                    runtime.handle_artifact_upload_ack(frame)
        finally:
            hb_task.cancel()


def cmd_serve(args: argparse.Namespace) -> int:
    from app.worker.daemon import run_daemon

    run_daemon(host=args.host, port=args.port, uds=args.uds)
    return 0


def cmd_desktop_host(args: argparse.Namespace) -> int:
    from app.worker.desktop_host import run_desktop_host_sync

    run_desktop_host_sync(ipc_uds=args.ipc_uds, stream_uds=args.stream_uds)
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    saved = cred_svc.load_credentials()
    cloud_url = (args.cloud_url or (saved or {}).get("cloud_url") or "").strip().rstrip("/")
    token = (saved or {}).get("worker_session_token")
    if not cloud_url or not token:
        print("not logged in; run: auto-agent-worker login", file=sys.stderr)
        return 1

    status = _fetch_worker_status(cloud_url, token)
    if status is None:
        print("无法验证 worker 状态，请重新登录。", file=sys.stderr)
        return 1
    approval = status.get("approval_status", "approved")
    if approval == "rejected":
        print("此设备已被管理员拒绝。", file=sys.stderr)
        return 1
    if approval == "pending":
        if _wait_for_approval(cloud_url, token) != 0:
            return 1

    env = asyncio.run(preflight.run_doctor(cloud_url, agent_version=AGENT_VERSION))
    if env.get("environment_status") == "not_ready":
        print("environment not ready; run: auto-agent-worker doctor", file=sys.stderr)
        print(json.dumps(env, indent=2))
        return 1

    print(f"connecting to {cloud_url} …")
    from app.worker.llm_proxy import install_llm_proxy

    install_llm_proxy(cloud_url=cloud_url, token=token)
    try:
        asyncio.run(_run_worker_loop(cloud_url, token, env))
    except KeyboardInterrupt:
        print("stopped")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    _frozen_bootstrap()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="auto-agent-worker")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="run environment preflight checks")
    doctor.add_argument("--cloud-url", default=None)
    doctor.set_defaults(func=cmd_doctor)

    login = sub.add_parser("login", help="authenticate with the cloud")
    login.add_argument("--cloud-url", default=None)
    login.add_argument("--email", default=None)
    login.add_argument("--password", default=None)
    login.add_argument("--display-name", default=None)
    login.add_argument("--machine-id", default=None)
    login.add_argument("--tags", nargs="*", default=None)
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser("logout", help="clear saved credentials")
    logout.set_defaults(func=cmd_logout)

    start = sub.add_parser("start", help="connect and execute dispatched runs")
    start.add_argument("--cloud-url", default=None)
    start.set_defaults(func=cmd_start)

    install_browsers = sub.add_parser(
        "install-browsers",
        help="download Chromium for Playwright (run once after installing the worker)",
    )
    install_browsers.set_defaults(func=cmd_install_browsers)

    serve = sub.add_parser(
        "serve",
        help="run desktop runtime sidecar (localhost HTTP API + worker WebSocket)",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=3921)
    serve.add_argument(
        "--uds",
        default=None,
        help="Unix domain socket path (monolith desktop; no TCP port)",
    )
    serve.set_defaults(func=cmd_serve)

    desktop_host = sub.add_parser(
        "desktop-host",
        help="run desktop runtime (framed JSON IPC + optional stream relay UDS)",
    )
    desktop_host.add_argument(
        "--ipc-uds",
        required=True,
        help="Unix socket for framed JSON RPC (Phase 4B)",
    )
    desktop_host.add_argument(
        "--stream-uds",
        default=None,
        help="Unix socket for HTTP SSE/WS relay until stream IPC lands",
    )
    desktop_host.set_defaults(func=cmd_desktop_host)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
