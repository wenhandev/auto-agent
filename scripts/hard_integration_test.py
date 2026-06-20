#!/usr/bin/env python3
"""Hard integration scenarios against a running auto_agent backend.

Usage (backend on :8001):
    python scripts/hard_integration_test.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import websockets

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

PORT = os.environ.get("AUTO_AGENT_PORT", "8001")
BASE = f"http://127.0.0.1:{PORT}"
WS = f"ws://127.0.0.1:{PORT}/ws/run"
MAX_TASK_SECONDS = 300  # 5 min per task


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _summarize_events(events: list[dict]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    errors: list[str] = []
    for ev in events:
        et = ev.get("event") or ev.get("event_type") or "unknown"
        by_type[et] = by_type.get(et, 0) + 1
        if et in ("node_failed", "run_failed", "validation_failed", "task_reflection"):
            err = ev.get("error") or ev.get("message") or ev.get("payload")
            if err:
                errors.append(str(err)[:300])
    return {"counts": by_type, "errors": errors[:10]}


def save_workflow_via_db(name: str, wf_json: dict) -> str:
    from sqlmodel import Session

    from app.db.session import engine
    from app.services import workflows as wf_svc

    with Session(engine) as session:
        wf = wf_svc.create_workflow(
            name=name,
            session=session,
            description="hard integration test workflow",
            initial_workflow_json=wf_json,
            authored_by="planner",
        )
        return wf.id


def build_hn_workflow() -> dict:
    """Fallback multi-step workflow: navigate → wait → vision_extract → validation."""
    return {
        "nodes": [
            {"id": "start", "type": "start", "label": "开始", "params": {}},
            {
                "id": "nav1",
                "type": "navigate",
                "label": "打开 HN",
                "params": {"url": "https://news.ycombinator.com"},
            },
            {
                "id": "wait1",
                "type": "wait",
                "label": "等待加载",
                "params": {"ms": 3000},
            },
            {
                "id": "extract1",
                "type": "vision_extract",
                "label": "提取头条",
                "params": {
                    "instruction": "Extract the top 5 story titles and their URLs from the front page.",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "stories": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["title"],
                                },
                                "minItems": 1,
                            }
                        },
                        "required": ["stories"],
                    },
                },
            },
            {
                "id": "valid1",
                "type": "validation",
                "label": "验证条数",
                "params": {
                    "predicate": {
                        "left": "{{= len(nodes.extract1.output.data.stories) }}",
                        "op": ">=",
                        "right": 3,
                    }
                },
                "on_error": "fail_run",
            },
            {"id": "end1", "type": "end", "label": "结束", "params": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "nav1"},
            {"id": "e2", "source": "nav1", "target": "wait1"},
            {"id": "e3", "source": "wait1", "target": "extract1"},
            {"id": "e4", "source": "extract1", "target": "valid1"},
            {"id": "e5", "source": "valid1", "target": "end1"},
        ],
        "start_id": "start",
        "parameters": [],
    }


async def monitor_task(http: httpx.AsyncClient, run_id: str, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_TASK_SECONDS
    last_status = ""
    events: list[dict] = []
    result: dict[str, Any] = {
        "run_id": run_id,
        "label": label,
        "pass": False,
        "final_status": None,
        "error": None,
        "result": None,
        "events_summary": {},
        "notable_events": [],
    }

    while time.monotonic() < deadline:
        try:
            r = await http.get(f"/api/tasks/{run_id}")
            if r.status_code == 200:
                body = r.json()
                status = body.get("status")
                if status != last_status:
                    print(f"  [{_ts()}] {label} status -> {status}", flush=True)
                    last_status = status
                if status in ("completed", "failed", "aborted", "completed_with_errors", "rejected"):
                    result["final_status"] = status
                    result["error"] = body.get("error")
                    result["result"] = body.get("result")
                    result["pass"] = status == "completed" and bool(
                        (body.get("result") or {}).get("success")
                    )
                    break
        except Exception as exc:
            print(f"  [{_ts()}] poll error: {exc}", flush=True)

        try:
            replay = await http.get(f"/api/runs/{run_id}/replay")
            if replay.status_code == 200:
                events = replay.json().get("events") or []
        except Exception:
            pass

        await asyncio.sleep(5)

    if result["final_status"] is None:
        result["final_status"] = "timeout"
        result["error"] = f"exceeded {MAX_TASK_SECONDS}s"

    try:
        replay = await http.get(f"/api/runs/{run_id}/replay")
        if replay.status_code == 200:
            events = replay.json().get("events") or []
    except Exception:
        pass

    result["events_summary"] = _summarize_events(events)
    for ev in events:
        et = ev.get("event_type") or ev.get("event")
        if et in (
            "task_plan_updated",
            "task_reflection",
            "task_finished",
            "node_failed",
            "run_failed",
            "vision_step",
        ):
            payload = ev.get("payload_json") or ev
            result["notable_events"].append(
                {"type": et, "detail": json.dumps(payload, ensure_ascii=False)[:400]}
            )

    return result


async def monitor_workflow_run(http: httpx.AsyncClient, run_id: str, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_TASK_SECONDS
    events: list[dict] = []
    terminal = False
    result: dict[str, Any] = {
        "run_id": run_id,
        "label": label,
        "pass": False,
        "final_status": None,
        "error": None,
        "events_summary": {},
        "notable_events": [],
        "node_outputs": {},
    }

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "run_id": run_id}))
        while time.monotonic() < deadline and not terminal:
            try:
                raw = await asyncio.wait_for(
                    ws.recv(), timeout=min(10, deadline - time.monotonic())
                )
                msg = json.loads(raw)
                events.append(msg)
                ev = msg.get("event")
                nid = msg.get("node_id")
                if ev == "node_started":
                    print(f"  [{_ts()}] {label} node_started {nid}", flush=True)
                elif ev == "node_completed":
                    out = msg.get("output")
                    result["node_outputs"][nid or "?"] = out
                    preview = json.dumps(out, ensure_ascii=False)[:200] if out else ""
                    print(f"  [{_ts()}] {label} node_completed {nid} {preview}", flush=True)
                elif ev == "node_failed":
                    print(
                        f"  [{_ts()}] {label} node_failed {nid} err={msg.get('error')!r}",
                        flush=True,
                    )
                elif ev == "validation_failed":
                    print(f"  [{_ts()}] {label} validation_failed {msg}", flush=True)
                elif ev == "vision_step":
                    step = msg.get("action") or msg.get("tool") or msg.get("summary")
                    print(f"  [{_ts()}] {label} vision_step {step}", flush=True)
                elif ev in ("run_completed", "run_failed", "run_aborted", "run_completed_with_errors"):
                    terminal = True
                    result["final_status"] = ev.replace("run_", "")
                    result["error"] = msg.get("error")
                    print(f"  [{_ts()}] {label} {ev}", flush=True)
            except asyncio.TimeoutError:
                pass
            except websockets.ConnectionClosed:
                break

    try:
        r = await http.get(f"/api/runs/{run_id}")
        if r.status_code == 200:
            run_body = r.json().get("run") or {}
            db_status = run_body.get("status")
            if db_status:
                result["final_status"] = db_status
                result["error"] = run_body.get("error")
    except Exception:
        pass

    if result["final_status"] is None:
        result["final_status"] = "timeout"

    result["pass"] = result["final_status"] == "completed"
    result["events_summary"] = _summarize_events(events)
    for ev in events[-30:]:
        et = ev.get("event")
        if et in ("node_failed", "validation_failed", "run_failed", "vision_step"):
            result["notable_events"].append(
                {"type": et, "detail": json.dumps(ev, ensure_ascii=False)[:400]}
            )
    return result


async def run_task_a(http: httpx.AsyncClient) -> dict[str, Any]:
    print("\n=== Hard Task A: Autonomous vision (Apple CN prices) ===", flush=True)
    body = {
        "objective": (
            "Go to apple.com.cn, find the current iPhone 16 Pro base model price in CNY, "
            "compare with MacBook Air M4 lowest price, return JSON with both prices and URLs."
        ),
        "start_url": "https://www.apple.com.cn",
        "max_steps": 45,
        "max_seconds": MAX_TASK_SECONDS,
        "allowed_domains": ["apple.com.cn", "www.apple.com.cn"],
        "data_schema": {
            "type": "object",
            "properties": {
                "iphone_16_pro_price_cny": {"type": "string"},
                "iphone_16_pro_url": {"type": "string"},
                "macbook_air_m4_price_cny": {"type": "string"},
                "macbook_air_m4_url": {"type": "string"},
                "comparison": {"type": "string"},
            },
            "required": ["iphone_16_pro_price_cny", "macbook_air_m4_price_cny"],
        },
        "synthesize_workflow": False,
    }
    r = await http.post("/api/tasks", json=body)
    if r.status_code != 200:
        return {
            "label": "Task A",
            "pass": False,
            "error": f"POST /api/tasks HTTP {r.status_code}: {r.text[:300]}",
        }
    task = r.json()
    run_id = task["id"]
    print(f"  created task run_id={run_id} status={task['status']}", flush=True)
    return await monitor_task(http, run_id, "Task A")


async def run_task_b(http: httpx.AsyncClient) -> dict[str, Any]:
    print("\n=== Hard Task B: Multi-step workflow (HN extract + validation) ===", flush=True)
    description = (
        "打开 https://news.ycombinator.com，等待3秒，"
        "用 vision_extract 提取前5条新闻标题和链接为 JSON stories 数组，"
        "然后用 validation 节点验证 stories 长度 >= 3"
    )
    wf_json: dict | None = None
    planner_note = ""
    try:
        gen = await http.post(
            "/api/workflow/generate",
            json={"description": description},
            timeout=120.0,
        )
        if gen.status_code == 200:
            wf_json = gen.json()
            types = [n.get("type") for n in wf_json.get("nodes") or []]
            print(f"  planner returned nodes: {types}", flush=True)
            if "vision_extract" not in types:
                planner_note = "planner missing vision_extract; using fallback"
                wf_json = None
        else:
            planner_note = f"planner HTTP {gen.status_code}"
    except Exception as exc:
        planner_note = f"planner error: {exc}"

    if wf_json is None:
        print(f"  using hand-built HN workflow ({planner_note})", flush=True)
        wf_json = build_hn_workflow()

    wf_id = save_workflow_via_db(f"hard-test-b-{int(time.time())}", wf_json)
    print(f"  saved workflow id={wf_id}", flush=True)

    r = await http.post(f"/api/workflows/{wf_id}/runs")
    if r.status_code != 200:
        return {
            "label": "Task B",
            "pass": False,
            "error": f"POST runs HTTP {r.status_code}: {r.text[:300]}",
        }
    run = r.json()
    run_id = run["id"]
    print(f"  enqueued run_id={run_id} status={run['status']}", flush=True)
    out = await monitor_workflow_run(http, run_id, "Task B")
    out["workflow_id"] = wf_id
    out["planner_note"] = planner_note
    return out


async def main() -> int:
    timeout = httpx.Timeout(120.0, connect=15.0)
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(base_url=BASE, timeout=timeout, trust_env=False) as http:
        for _ in range(20):
            try:
                h = await http.get("/api/health")
                if h.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        else:
            print("FAIL: backend not healthy", file=sys.stderr)
            return 2

        print(f"Backend OK at {BASE}", flush=True)

        results.append(await run_task_b(http))
        await asyncio.sleep(3)
        results.append(await run_task_a(http))

    report_path = Path(__file__).resolve().parents[1] / "hard_integration_report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===", flush=True)
    for r in results:
        label = r.get("label") or r.get("run_id", "?")
        status = "PASS" if r.get("pass") else "FAIL"
        print(
            f"  [{status}] {label} run_id={r.get('run_id')} "
            f"final={r.get('final_status')} error={r.get('error')!r}",
            flush=True,
        )
        if r.get("result"):
            print(f"         result={json.dumps(r['result'], ensure_ascii=False)[:300]}", flush=True)
        es = r.get("events_summary") or {}
        if es.get("errors"):
            print(f"         errors={es['errors'][:3]}", flush=True)

    print(f"\nFull report: {report_path}", flush=True)
    return 0 if any(r.get("pass") for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
