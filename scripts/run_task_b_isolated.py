#!/usr/bin/env python3
"""Run Task B in isolation with WS monitoring."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(ROOT))

from scripts.hard_integration_test import build_hn_workflow, monitor_workflow_run, save_workflow_via_db

BASE = "http://127.0.0.1:8001"


async def main() -> int:
    wf_id = save_workflow_via_db(f"hard-b-isolated", build_hn_workflow())
    async with httpx.AsyncClient(base_url=BASE, timeout=120.0, trust_env=False) as http:
        r = await http.post(f"/api/workflows/{wf_id}/runs")
        run = r.json()
        run_id = run["id"]
        print(f"run_id={run_id} status={run['status']}", flush=True)
        result = await monitor_workflow_run(http, run_id, "Task B isolated")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("pass") else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
