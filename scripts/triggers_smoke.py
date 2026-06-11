"""Smoke test for the triggers-and-scheduling feature.

Boots its own uvicorn on a free port to avoid colliding with any other
dev backend (e.g. the parallel sibling worker). Creates a webhook +
cron trigger, fires the webhook, validates auth, checks the scheduler
debug endpoint shows the cron job, then deletes both.

Usage:
    cd backend
    .venv\\Scripts\\python.exe ..\\scripts\\triggers_smoke.py

Exits 0 on success.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(client: httpx.Client, base: str, *, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = client.get(f"{base}/api/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise RuntimeError(f"backend never became healthy: {last_err}")


def _seed_workflow(client: httpx.Client, base: str) -> str:
    r = client.get(f"{base}/api/workflows")
    r.raise_for_status()
    rows = r.json()
    if rows:
        return rows[0]["id"]
    r = client.post(
        f"{base}/api/workflows",
        json={"name": "smoke-trigger-wf", "description": "trigger smoke"},
    )
    r.raise_for_status()
    return r.json()["id"]


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run_smoke(base: str) -> int:
    with httpx.Client(trust_env=False, timeout=10.0) as client:
        _wait_health(client, base, timeout=45.0)
        wf_id = _seed_workflow(client, base)
        print(f"[smoke] using workflow_id={wf_id}")

        r = client.post(
            f"{base}/api/workflows/{wf_id}/triggers",
            json={"type": "webhook"},
        )
        _assert(r.status_code == 200, f"create webhook -> {r.status_code} {r.text}")
        webhook = r.json()
        webhook_id = webhook["id"]
        webhook_secret = webhook["secret_full"]
        webhook_path = webhook["schedule_or_path"]
        _assert(bool(webhook_secret), "webhook secret_full missing")
        print(f"[smoke] created webhook trigger id={webhook_id} path={webhook_path}")

        body = {"order_id": "smoke-1", "amount": 42}
        r = client.post(
            f"{base}/api/triggers/webhook/{webhook_path}",
            params={"secret": webhook_secret},
            json=body,
        )
        _assert(r.status_code == 200, f"webhook fire -> {r.status_code} {r.text}")
        fire = r.json()
        run_id = fire["run_id"]
        print(f"[smoke] webhook fired ok, run_id={run_id}")

        time.sleep(0.4)
        rget = client.get(f"{base}/api/runs/{run_id}")
        _assert(rget.status_code == 200, f"run get -> {rget.status_code}")
        run_row = rget.json()["run"]
        _assert(
            run_row.get("source") == "webhook",
            f"expected run.source=webhook, got {run_row.get('source')}",
        )
        ctx = run_row.get("trigger_context") or {}
        _assert(
            ctx.get("kind") == "webhook",
            f"expected trigger_context.kind=webhook, got {ctx}",
        )
        _assert(
            (ctx.get("body") or {}).get("order_id") == "smoke-1",
            f"expected trigger_context.body.order_id=smoke-1, got {ctx.get('body')}",
        )
        print("[smoke] run row carries source=webhook and trigger_context")

        r = client.post(
            f"{base}/api/triggers/webhook/{webhook_path}",
            params={"secret": "obviously-wrong"},
            json={},
        )
        _assert(r.status_code == 401, f"wrong secret -> {r.status_code} {r.text}")
        print("[smoke] wrong secret correctly returns 401")

        r = client.post(
            f"{base}/api/triggers/webhook/nope-nope-nope",
            params={"secret": "x"},
            json={},
        )
        _assert(r.status_code == 404, f"unknown path -> {r.status_code} {r.text}")
        print("[smoke] unknown path correctly returns 404")

        r = client.post(
            f"{base}/api/workflows/{wf_id}/triggers",
            json={"type": "cron", "schedule_or_path": "*/2 * * * *"},
        )
        _assert(r.status_code == 200, f"create cron -> {r.status_code} {r.text}")
        cron_trig = r.json()
        cron_id = cron_trig["id"]
        print(f"[smoke] created cron trigger id={cron_id}")

        r = client.get(f"{base}/api/scheduler/_debug/jobs")
        _assert(
            r.status_code == 200,
            f"debug jobs (with AUTO_AGENT_DEBUG=1) -> {r.status_code} {r.text}",
        )
        jobs = r.json().get("jobs", [])
        job_ids = {j["id"] for j in jobs}
        _assert(
            f"trigger:{cron_id}" in job_ids,
            f"scheduler missing job for cron trigger {cron_id}; jobs={job_ids}",
        )
        print(f"[smoke] scheduler has {len(jobs)} job(s) incl. trigger:{cron_id}")

        r = client.delete(f"{base}/api/triggers/{cron_id}")
        _assert(r.status_code == 204, f"delete cron -> {r.status_code}")
        r = client.get(f"{base}/api/scheduler/_debug/jobs")
        jobs_after = {j["id"] for j in r.json().get("jobs", [])}
        _assert(
            f"trigger:{cron_id}" not in jobs_after,
            f"scheduler still has deleted cron trigger; jobs={jobs_after}",
        )
        print("[smoke] cron trigger deletion removed scheduler job")

        r = client.patch(
            f"{base}/api/triggers/{webhook_id}",
            json={"regenerate_secret": True},
        )
        _assert(
            r.status_code == 200,
            f"regenerate secret -> {r.status_code} {r.text}",
        )
        new_secret = r.json()["secret_full"]
        _assert(new_secret and new_secret != webhook_secret, "secret did not rotate")
        r = client.post(
            f"{base}/api/triggers/webhook/{webhook_path}",
            params={"secret": webhook_secret},
            json={},
        )
        _assert(
            r.status_code == 401,
            f"old secret must be rejected after rotate -> {r.status_code}",
        )
        r = client.post(
            f"{base}/api/triggers/webhook/{webhook_path}",
            params={"secret": new_secret},
            json={"rotated": True},
        )
        _assert(
            r.status_code == 200,
            f"new secret must work after rotate -> {r.status_code} {r.text}",
        )
        print("[smoke] secret rotation works (old=401, new=200)")

        r = client.delete(f"{base}/api/triggers/{webhook_id}")
        _assert(r.status_code == 204, f"delete webhook -> {r.status_code}")
        r = client.post(
            f"{base}/api/triggers/webhook/{webhook_path}",
            params={"secret": new_secret},
            json={},
        )
        _assert(
            r.status_code == 404,
            f"deleted webhook must 404 -> {r.status_code}",
        )
        print("[smoke] webhook trigger deletion -> 404 on subsequent fire")

    print("[smoke] ALL CHECKS PASSED")
    return 0


def main() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["AUTO_AGENT_PORT"] = str(port)
    env["AUTO_AGENT_DEBUG"] = "1"
    env["NO_PROXY"] = "127.0.0.1,localhost"

    cmd = [
        str(BACKEND_DIR / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    print(f"[smoke] booting backend on {base}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        rc = run_smoke(base)
    except Exception:
        import traceback

        traceback.print_exc()
        rc = 1
    finally:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception:
            pass
        if proc.stdout is not None:
            tail = proc.stdout.read().decode("utf-8", errors="replace")
            if tail.strip():
                print("[smoke] --- backend output (tail) ---")
                print(tail[-2000:])
    return rc


if __name__ == "__main__":
    sys.exit(main())
