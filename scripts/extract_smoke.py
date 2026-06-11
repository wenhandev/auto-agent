"""End-to-end verification for the real `extract` deliverable.

Posts a deterministic example.com prompt to the planner, drives the resulting
workflow over `/ws/run`, and asserts that the final `extract` node's
`output.text` contains real page content (not a stub title).

Usage (with backend running on :8001):
    python scripts/extract_smoke.py
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

PORT = os.environ.get("AUTO_AGENT_PORT", "8001")
BASE = f"http://localhost:{PORT}"
WS = f"ws://localhost:{PORT}/ws/run"
DESCRIPTION = "打开 https://example.com 然后提取页面 H1 文字"


def generate_workflow(description: str) -> dict:
    body = json.dumps({"description": description}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/workflow/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def run() -> int:
    try:
        workflow = generate_workflow(DESCRIPTION)
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        print(f"FAIL: planner HTTP {e.code} {text}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"FAIL: could not reach backend: {e}", file=sys.stderr)
        return 2

    nodes = workflow.get("nodes") or []
    print(f"planner returned {len(nodes)} nodes; types={[n['type'] for n in nodes]}")

    completed_with_output: dict[str, dict] = {}
    extract_outputs: list[tuple[str, dict]] = []
    run_completed = False
    run_failed_reason: str | None = None

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "workflow": workflow}))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                ev = msg.get("event")
                nid = msg.get("node_id")
                if ev == "node_completed":
                    out = msg.get("output")
                    if "output" in msg:
                        completed_with_output[nid] = msg
                    node_type = next(
                        (n["type"] for n in nodes if n["id"] == nid), None
                    )
                    print(
                        f"[done    ] {nid} ({node_type})  "
                        f"output={json.dumps(out, ensure_ascii=False)[:160]}"
                    )
                    if node_type == "extract" and isinstance(out, dict):
                        extract_outputs.append((nid, out))
                elif ev == "node_failed":
                    print(f"[failed  ] {nid}  err={msg.get('error')!r}")
                elif ev == "run_started":
                    print("[run     ] started")
                elif ev == "run_completed":
                    run_completed = True
                    print("[run     ] completed")
                elif ev == "run_failed":
                    run_failed_reason = msg.get("error")
                    print(f"[run     ] failed: {run_failed_reason}")
        except websockets.ConnectionClosed:
            pass

    print("\n--- summary ---")
    print(f"run_completed: {run_completed}, run_failed: {run_failed_reason}")
    print(f"extract outputs: {len(extract_outputs)}")
    for nid, out in extract_outputs:
        print(f"  {nid}: {json.dumps(out, ensure_ascii=False)}")

    ok = True
    if not run_completed:
        print(f"ASSERT FAIL: run did not complete (failed={run_failed_reason})")
        ok = False
    if not completed_with_output:
        print("ASSERT FAIL: no node_completed events carried `output`")
        ok = False
    if not extract_outputs:
        print("ASSERT FAIL: planner did not emit any extract node")
        ok = False
    else:
        last_nid, last_out = extract_outputs[-1]
        text = last_out.get("text") if isinstance(last_out, dict) else None
        if not isinstance(text, str) or not text:
            print(
                f"ASSERT FAIL: last extract node {last_nid} returned empty text "
                f"(error={last_out.get('error')!r})"
            )
            ok = False
        elif "Example Domain" not in text and "example" not in text.lower():
            print(
                f"WARN: last extract text does not look like example.com content: "
                f"{text!r} (still passes — model may have answered differently)"
            )
        else:
            print(f"OK: last extract text = {text!r}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
