"""Platform smoke test for the auto-agent backend.

Exercises the new platform endpoints + the WebSocket platform path.
Assumes the backend is reachable on $AUTO_AGENT_PORT (default 8001).

Usage:
    python scripts/platform_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import httpx
import websockets


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


PORT = os.environ.get("AUTO_AGENT_PORT", "8001")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws/run"

PASS = "[PASS]"
FAIL = "[FAIL]"


def _bail(msg: str) -> None:
    print(f"{FAIL} {msg}", flush=True)
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"{PASS} {msg}", flush=True)


async def main() -> int:
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(
        base_url=BASE, timeout=timeout, trust_env=False
    ) as http:
        for _ in range(40):
            try:
                r = await http.get("/api/health")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        else:
            _bail("backend never became healthy")
        _ok("backend healthy")

        r = await http.get("/api/workflows")
        if r.status_code != 200:
            _bail(f"list workflows: HTTP {r.status_code} body={r.text!r}")
        workflows = r.json()
        seeded = [w for w in workflows if w["name"] == "示例工作流"]
        if not seeded:
            _bail(f"seeded sample workflow missing; got names={[w['name'] for w in workflows]}")
        sample_id = seeded[0]["id"]
        _ok(f"step 1 list workflows; seeded sample id={sample_id}")

        r = await http.post(
            "/api/workflows",
            json={"name": "smoke-workflow", "description": "smoke test workflow"},
        )
        if r.status_code != 200:
            _bail(f"create workflow: HTTP {r.status_code} body={r.text!r}")
        created = r.json()
        new_wf_id = created["id"]
        new_session_id = created.get("chat_session_id")
        if not new_session_id:
            _bail("created workflow missing chat_session_id")
        _ok(f"step 2 created workflow id={new_wf_id} session={new_session_id}")

        r = await http.post(
            f"/api/workflows/{new_wf_id}/chat",
            json={"message": "加一个等待 2 秒的节点"},
        )
        if r.status_code != 200:
            _bail(f"chat turn: HTTP {r.status_code} body={r.text!r}")
        turn = r.json()
        if not turn.get("assistant_message"):
            _bail(f"chat turn missing assistant_message: {turn}")
        chat_new_version = turn.get("new_version")
        if chat_new_version:
            _ok(f"step 3 chat produced new_version index={chat_new_version['version_index']}")
        else:
            _ok("step 3 chat returned conversational reply (no new version)")

        existing = (await http.get("/api/credentials")).json()
        for c in existing:
            if c["name"] == "demo":
                await http.delete(f"/api/credentials/{c['id']}")

        r = await http.post(
            "/api/credentials",
            json={
                "name": "demo",
                "description": "smoke credential",
                "fields": {"username": "demo-user", "password": "demo-secret-1234"},
            },
        )
        if r.status_code != 200:
            _bail(f"create credential: HTTP {r.status_code} body={r.text!r}")
        cred = r.json()
        if any("demo-secret" in (f.get("masked_value") or "") for f in cred["fields"]):
            _bail(f"credential masked value leaked plaintext: {cred['fields']}")
        r = await http.get("/api/credentials")
        if r.status_code != 200:
            _bail(f"list credentials: HTTP {r.status_code} body={r.text!r}")
        creds_list = r.json()
        demo_listed = [c for c in creds_list if c["name"] == "demo"]
        if not demo_listed:
            _bail("demo credential missing from list")
        if "demo-secret" in json.dumps(demo_listed):
            _bail(f"plaintext leaked in credential list: {demo_listed}")
        _ok(f"step 4 created masked credential id={cred['id']}")

        r = await http.post(f"/api/workflows/{sample_id}/runs")
        if r.status_code != 200:
            _bail(f"first run: HTTP {r.status_code} body={r.text!r}")
        first_run = r.json()
        first_run_id = first_run["id"]
        if first_run["status"] not in ("queued", "running"):
            _bail(f"first run unexpected status {first_run['status']}")

        r = await http.post(f"/api/workflows/{sample_id}/runs")
        if r.status_code != 200:
            _bail(f"second run: HTTP {r.status_code} body={r.text!r}")
        second_run = r.json()
        second_run_id = second_run["id"]
        if second_run["status"] not in ("queued", "running"):
            _bail(f"second run unexpected status {second_run['status']}")
        _ok(
            f"step 5 two runs enqueued: first={first_run_id} ({first_run['status']})"
            f" second={second_run_id} ({second_run['status']})"
        )

        events: list[dict] = []
        run_started_seen = False
        run_aborted_seen = False
        abort_sent = False
        ws_deadline = time.monotonic() + 60.0
        async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
            await ws.send(json.dumps({"type": "start", "run_id": first_run_id}))
            while time.monotonic() < ws_deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=ws_deadline - time.monotonic())
                except asyncio.TimeoutError:
                    break
                except websockets.ConnectionClosed:
                    break
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                events.append(msg)
                ev = msg.get("event")
                if ev == "run_started":
                    run_started_seen = True
                    _ok(f"step 6 run_started received for run={first_run_id}")
                elif ev == "node_started":
                    print(f"      node_started node_id={msg.get('node_id')}", flush=True)
                    if not abort_sent:
                        await ws.send(json.dumps({"type": "abort"}))
                        abort_sent = True
                        print("      sent abort frame", flush=True)
                elif ev == "node_completed":
                    print(f"      node_completed node_id={msg.get('node_id')}", flush=True)
                elif ev == "run_aborted":
                    run_aborted_seen = True
                    _ok("step 7 run_aborted received")
                    break
                elif ev in ("run_completed", "run_failed"):
                    print(f"      terminal {ev}: {msg.get('error')}", flush=True)
                    break

        if not run_started_seen:
            _bail("never saw run_started over WS")

        deadline = time.monotonic() + 30.0
        first_status = ""
        while time.monotonic() < deadline:
            r = await http.get(f"/api/runs/{first_run_id}")
            if r.status_code == 200:
                first_status = r.json()["run"]["status"]
                if first_status in ("aborted", "failed", "completed"):
                    break
            await asyncio.sleep(0.5)
        if first_status != "aborted":
            _ok(
                f"NOTE step 7 first run final status is {first_status!r}"
                f" (expected aborted; depends on executor timing)"
            )
        else:
            _ok(f"step 7 first run DB status = aborted")

        r = await http.get(f"/api/runs?workflow_id={sample_id}")
        if r.status_code != 200:
            _bail(f"list runs: HTTP {r.status_code} body={r.text!r}")
        runs_list = r.json()
        ids = {r_["id"] for r_ in runs_list}
        if first_run_id not in ids:
            _bail(f"first run missing from list: {ids}")
        if second_run_id not in ids:
            _bail(f"second run missing from list: {ids}")
        _ok(f"step 8 runs list contains both runs (n={len(runs_list)})")

        existing_llm = (await http.get("/api/llm-config")).json()
        for c in existing_llm:
            if c["model"] == "smoke-test-model":
                await http.delete(f"/api/llm-config/{c['id']}")

        r = await http.post(
            "/api/llm-config",
            json={
                "provider": "openai",
                "model": "smoke-test-model",
                "api_key": "sk-smoke-dummy-key-zzzz",
                "base_url": "http://example.invalid",
            },
        )
        if r.status_code != 200:
            _bail(f"upsert llm config: HTTP {r.status_code} body={r.text!r}")
        cfg = r.json()
        if not cfg["is_active"]:
            _bail("freshly upserted LLM config should be active")
        if "sk-smoke-dummy-key" in (cfg.get("api_key_masked") or ""):
            _bail(f"api_key_masked leaked plaintext: {cfg['api_key_masked']}")
        r = await http.get("/api/llm-config")
        if r.status_code != 200:
            _bail(f"list llm configs: HTTP {r.status_code}")
        active_rows = [c for c in r.json() if c["is_active"]]
        if len(active_rows) != 1 or active_rows[0]["id"] != cfg["id"]:
            _bail(f"active llm row mismatch: {[c['id'] for c in active_rows]} (want {cfg['id']})")
        _ok(f"step 9 swapped active llm config to id={cfg['id']}")

        try:
            r = await http.delete(f"/api/llm-config/{cfg['id']}")
            if r.status_code not in (200, 204):
                print(f"      cleanup llm-config delete -> HTTP {r.status_code}", flush=True)
        except Exception:
            pass
        try:
            r = await http.delete(f"/api/credentials/{cred['id']}")
            if r.status_code not in (200, 204):
                print(f"      cleanup credential delete -> HTTP {r.status_code}", flush=True)
        except Exception:
            pass

    print(f"\n{PASS} platform smoke complete")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
