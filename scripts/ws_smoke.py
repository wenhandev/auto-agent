"""Smoke-test the /ws/run WebSocket against a running backend.

Usage (with the backend venv activated and the server running on :8000):
    python scripts/ws_smoke.py

Exits 0 on success. Asserts on the expected event sequence for the sample workflow.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.error
import urllib.request

import websockets

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PORT = os.environ.get("AUTO_AGENT_PORT", "8000")
BASE = f"http://localhost:{PORT}"
WS = f"ws://localhost:{PORT}/ws/run"


def fetch_sample() -> dict:
    with urllib.request.urlopen(f"{BASE}/api/sample-workflow", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def run() -> int:
    try:
        workflow = fetch_sample()
    except urllib.error.URLError as e:
        print(f"FAIL: could not GET /api/sample-workflow: {e}", file=sys.stderr)
        return 2

    print(f"got sample workflow: {len(workflow['nodes'])} nodes, start_id={workflow['start_id']}")

    started: set[str] = set()
    completed: set[str] = set()
    failed: set[str] = set()
    progress_for: dict[str, int] = {}
    run_completed = False
    run_failed_reason: str | None = None

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "workflow": workflow}))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                ev = msg.get("event")
                nid = msg.get("node_id")
                if ev == "node_started":
                    started.add(nid)
                    print(f"[started ] {nid}")
                elif ev == "node_progress":
                    progress_for[nid] = progress_for.get(nid, 0) + 1
                    print(f"[progress] {nid}  {msg.get('message')!r}")
                elif ev == "node_completed":
                    completed.add(nid)
                    print(f"[done    ] {nid}")
                elif ev == "node_failed":
                    failed.add(nid)
                    print(f"[failed  ] {nid}  err={msg.get('error')!r}")
                elif ev == "run_started":
                    print("[run     ] started")
                elif ev == "run_completed":
                    run_completed = True
                    print("[run     ] completed")
                elif ev == "run_failed":
                    run_failed_reason = msg.get("error")
                    print(f"[run     ] failed: {run_failed_reason}")
                else:
                    print(f"[?       ] {msg}")
        except websockets.ConnectionClosed:
            pass

    print("\n--- summary ---")
    print(f"started:   {sorted(started)}")
    print(f"completed: {sorted(completed)}")
    print(f"failed:    {sorted(failed)}")
    print(f"progress:  {progress_for}")
    print(f"run_completed: {run_completed}, run_failed: {run_failed_reason}")

    expected_nodes = {n["id"] for n in workflow["nodes"]}
    fuzzy_ids = {n["id"] for n in workflow["nodes"] if n["type"] == "fuzzy_action"}

    ok = True
    if started != expected_nodes:
        print(f"ASSERT FAIL: started ({started}) != expected ({expected_nodes})")
        ok = False
    if completed | failed != expected_nodes:
        print(
            f"ASSERT FAIL: completed|failed ({completed | failed}) != expected ({expected_nodes})"
        )
        ok = False
    for fid in fuzzy_ids:
        if progress_for.get(fid, 0) < 1:
            print(f"ASSERT FAIL: fuzzy node {fid} emitted no node_progress events")
            ok = False
    if not run_completed and not run_failed_reason:
        print("ASSERT FAIL: neither run_completed nor run_failed emitted")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
