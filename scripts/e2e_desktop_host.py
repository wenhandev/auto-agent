#!/usr/bin/env python3
"""E2E smoke test for release desktop-host IPC + stream relay."""

from __future__ import annotations

import json
import socket
import struct
import subprocess
import sys
import uuid
from typing import Any

IPC_SOCK = __import__("os").path.expanduser(
    "~/Library/Application Support/com.autoagent.client/runtime-ipc.sock"
)
STREAM_SOCK = __import__("os").path.expanduser(
    "~/Library/Application Support/com.autoagent.client/runtime-stream.sock"
)
CLOUD = "https://rpa.wenhandev.com"


def ipc_call(method: str, params: dict | None = None) -> dict[str, Any]:
    params = params or {}
    req = json.dumps({"v": 1, "id": str(uuid.uuid4()), "method": method, "params": params}).encode()
    frame = struct.pack(">I", len(req)) + req
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(15)
    try:
        s.connect(IPC_SOCK)
        s.sendall(frame)
        hdr = _recv_exact(s, 4)
        body = _recv_exact(s, int.from_bytes(hdr, "big"))
        return json.loads(body.decode())
    finally:
        s.close()


def _recv_exact(s: socket.socket, n: int) -> bytes:
    chunks: list[bytes] = []
    while len(b"".join(chunks)) < n:
        chunk = s.recv(n - len(b"".join(chunks)))
        if not chunk:
            raise OSError("socket closed early")
        chunks.append(chunk)
    return b"".join(chunks)


def curl_unix(path: str) -> tuple[int, str]:
    r = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "--unix-socket", STREAM_SOCK, f"http://localhost{path}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    out = r.stdout.rsplit("\n", 1)
    if len(out) == 2:
        return int(out[1]), out[0]
    return r.returncode, r.stdout


def ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main() -> int:
    print("=== Auto Agent desktop-host E2E ===\n")
    all_ok = True

    # Process check
    ps = subprocess.run(["pgrep", "-fl", "desktop-host"], capture_output=True, text=True)
    all_ok &= ok("desktop-host process running", "desktop-host" in ps.stdout, ps.stdout.strip() or "not found")

    # Port 3921
    lsof = subprocess.run(["lsof", "-i", ":3921"], capture_output=True, text=True)
    all_ok &= ok("no TCP 3921 listener", lsof.returncode != 0)

    # IPC health
    health = ipc_call("health")
    all_ok &= ok("IPC health", health.get("ok") and health.get("result", {}).get("status") == "ok", str(health))

    # IPC status
    status = ipc_call("status")
    if status.get("ok"):
        r = status["result"]
        detail = f"logged_in={r.get('logged_in')} connected={r.get('connected')} env={r.get('preflight', {}).get('environment_status')}"
        all_ok &= ok("IPC status", True, detail)
    else:
        all_ok &= ok("IPC status", False, str(status))

    # IPC ready (cloud reachability)
    ready = ipc_call("ready")
    if ready.get("ok"):
        r = ready["result"]
        all_ok &= ok("IPC ready", True, f"cloud={r.get('cloud')} status={r.get('status')}")
    else:
        all_ok &= ok("IPC ready", False, str(ready))

    # IPC doctor / preflight
    doctor = ipc_call("doctor")
    if doctor.get("ok"):
        r = doctor["result"]
        env = r.get("environment_status", "?")
        checks = {c["id"]: c["status"] for c in r.get("checks", [])}
        chromium = checks.get("chromium_binary", "?")
        all_ok &= ok("IPC doctor", env in ("ready", "degraded"), f"env={env} chromium={chromium}")
    else:
        all_ok &= ok("IPC doctor", False, str(doctor))

    # Stream relay health
    code, body = curl_unix("/health")
    all_ok &= ok("stream /health", code == 200 and "ok" in body, f"HTTP {code} {body[:80]}")

    # Cloud API direct
    cloud = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{CLOUD}/api/health"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    all_ok &= ok("cloud /api/health", cloud.stdout.strip() == "200", f"HTTP {cloud.stdout.strip()}")

    # drafts.list (may fail if not logged in - still valid response)
    drafts = ipc_call("drafts.list")
    if drafts.get("ok"):
        all_ok &= ok("IPC drafts.list", isinstance(drafts.get("result"), list), f"count={len(drafts['result'])}")
    else:
        err = drafts.get("error", {})
        all_ok &= ok("IPC drafts.list", False, err.get("message", str(drafts)))

    print("\n=== Summary ===")
    if all_ok:
        print("All checks passed.")
        return 0
    print("Some checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
