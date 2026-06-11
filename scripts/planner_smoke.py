"""Optional planner smoke-test against a running backend.

Skips cleanly (exit 0) if OPENAI_API_KEY / GOOGLE_API_KEY is not set or the backend
returns the documented 400 for missing keys.

Usage (with the backend running on :8000):
    python scripts/planner_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


PORT = os.environ.get("AUTO_AGENT_PORT", "8000")
BASE = f"http://localhost:{PORT}"
DESCRIPTION = "打开 https://example.com，等待 1 秒，然后跳转到 https://example.org"


def main() -> int:
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print("no LLM key in env; skipping planner smoke-test")
        return 0

    body = json.dumps({"description": DESCRIPTION}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/workflow/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        if e.code == 400 and "API key" in text:
            print(f"backend reports no API key (HTTP 400): {text}")
            return 0
        print(f"FAIL: HTTP {e.code} {text}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"FAIL: could not POST /api/workflow/generate: {e}", file=sys.stderr)
        return 2

    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    start_id = data.get("start_id")
    if not nodes:
        print("FAIL: empty nodes")
        return 1
    if not start_id or start_id not in {n["id"] for n in nodes}:
        print(f"FAIL: bad start_id {start_id!r}")
        return 1
    print(f"OK: planner returned {len(nodes)} nodes, {len(edges)} edges, start={start_id}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
