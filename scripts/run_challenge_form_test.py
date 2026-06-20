#!/usr/bin/env python3
"""Run auto_agent against the local captcha-style challenge form.

Usage (backend on :8001):
    python scripts/run_challenge_form_test.py
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
PAGE_URL = f"{BASE}/static/challenge-form.html"
MAX_SECONDS = 180


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def build_challenge_workflow(page_url: str) -> dict:
    """Deterministic fills + vision slider + submit + validation."""
    return {
        "nodes": [
            {"id": "start", "type": "start", "label": "开始", "params": {}},
            {
                "id": "nav",
                "type": "navigate",
                "label": "打开挑战表单",
                "params": {"url": page_url},
            },
            {
                "id": "wait_load",
                "type": "wait",
                "label": "等待加载",
                "params": {"ms": 800},
            },
            {
                "id": "fill_pw",
                "type": "fill",
                "label": "填写密码",
                "params": {"selector": "#password", "value": "SecretPass123"},
            },
            {
                "id": "drag_slider",
                "type": "fuzzy_action",
                "label": "拖动滑块验证",
                "params": {
                    "action": "drag_slider",
                    "thumb_selector": "#slider-thumb",
                    "track_selector": "#slider-track",
                },
            },
            {
                "id": "fill_name",
                "type": "fill",
                "label": "填写姓名",
                "params": {"selector": "#name", "value": "Jane Agent"},
            },
            {
                "id": "fill_email",
                "type": "fill",
                "label": "填写邮箱",
                "params": {"selector": "#email", "value": "jane.agent@example.com"},
            },
            {
                "id": "fill_phone",
                "type": "fill",
                "label": "填写电话",
                "params": {"selector": "#phone", "value": "+1 555 0199"},
            },
            {
                "id": "submit",
                "type": "click",
                "label": "提交表单",
                "params": {"selector": "#submit-btn"},
            },
            {
                "id": "wait_success",
                "type": "wait",
                "label": "等待成功面板",
                "params": {"ms": 500},
            },
            {
                "id": "valid",
                "type": "validation",
                "label": "验证提交成功",
                "params": {
                    "predicate": {
                        "left": "{{= nodes.drag_slider.output.verified_badge_visible }}",
                        "op": "==",
                        "right": True,
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "nav"},
            {"id": "e2", "source": "nav", "target": "wait_load"},
            {"id": "e3", "source": "wait_load", "target": "fill_pw"},
            {"id": "e4", "source": "fill_pw", "target": "drag_slider"},
            {"id": "e5", "source": "drag_slider", "target": "fill_name"},
            {"id": "e6", "source": "fill_name", "target": "fill_email"},
            {"id": "e7", "source": "fill_email", "target": "fill_phone"},
            {"id": "e8", "source": "fill_phone", "target": "submit"},
            {"id": "e9", "source": "submit", "target": "wait_success"},
            {"id": "e10", "source": "wait_success", "target": "valid"},
        ],
        "start_id": "start",
    }


def build_programmatic_workflow(page_url: str) -> dict:
    """Fallback workflow using direct drag via fuzzy_action instruction."""
    wf = build_challenge_workflow(page_url)
    wf["nodes"][4] = {
        "id": "drag_slider",
        "type": "fuzzy_action",
        "label": "拖动滑块验证",
        "params": {
            "instruction": (
                "Complete the slider verification: drag #slider-thumb to the right end of "
                "#slider-track using drag_element. Confirm Verified badge is visible."
            ),
        },
    }
    return wf


async def check_page_reachable(http: httpx.AsyncClient) -> tuple[bool, str]:
    for url in (PAGE_URL, f"http://127.0.0.1:5173/challenge-form.html"):
        try:
            r = await http.get(url)
            if r.status_code == 200 and "Secure Registration" in r.text:
                return True, url
        except Exception:
            pass
    return False, PAGE_URL


async def monitor_workflow(http: httpx.AsyncClient, wf_json: dict) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_SECONDS
    events: list[dict] = []
    result: dict[str, Any] = {
        "run_id": None,
        "pass": False,
        "final_status": None,
        "error": None,
        "node_outputs": {},
        "slider_notes": [],
        "notable_events": [],
    }

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "workflow": wf_json}))
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                events.append(msg)
                ev = msg.get("event")
                nid = msg.get("node_id")
                if ev == "run_started" and msg.get("run_id"):
                    result["run_id"] = msg["run_id"]
                if ev == "node_completed":
                    result["node_outputs"][nid or "?"] = msg.get("output")
                    if nid == "drag_slider":
                        out = msg.get("output") or {}
                        result["slider_notes"].append(json.dumps(out, ensure_ascii=False)[:300])
                elif ev == "vision_step":
                    action = msg.get("action") or ""
                    if "drag" in str(action).lower():
                        result["slider_notes"].append(f"vision_step: {action}")
                    result["notable_events"].append(
                        {"type": "vision_step", "detail": json.dumps(msg, ensure_ascii=False)[:300]}
                    )
                elif ev == "node_failed":
                    result["notable_events"].append(
                        {"type": "node_failed", "node": nid, "error": msg.get("error")}
                    )
                elif ev in ("run_completed", "run_failed", "run_aborted", "run_completed_with_errors"):
                    result["final_status"] = ev.replace("run_", "")
                    result["error"] = msg.get("error")
                    break
            except asyncio.TimeoutError:
                continue
            except websockets.ConnectionClosed:
                break

    if result["run_id"]:
        try:
            r = await http.get(f"/api/runs/{result['run_id']}")
            if r.status_code == 200:
                run_body = r.json().get("run") or {}
                if run_body.get("status"):
                    result["final_status"] = run_body["status"]
                    result["error"] = run_body.get("error")
        except Exception:
            pass

    result["pass"] = result["final_status"] == "completed"
    return result


async def monitor_run(http: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_SECONDS
    events: list[dict] = []
    result: dict[str, Any] = {
        "run_id": run_id,
        "pass": False,
        "final_status": None,
        "error": None,
        "node_outputs": {},
        "slider_notes": [],
        "notable_events": [],
    }

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "run_id": run_id}))
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                events.append(msg)
                ev = msg.get("event")
                nid = msg.get("node_id")
                if ev == "node_completed":
                    result["node_outputs"][nid or "?"] = msg.get("output")
                    if nid == "drag_slider":
                        out = msg.get("output") or {}
                        result["slider_notes"].append(json.dumps(out, ensure_ascii=False)[:300])
                elif ev == "vision_step":
                    action = msg.get("action") or ""
                    if "drag" in str(action).lower():
                        result["slider_notes"].append(f"vision_step: {action}")
                    result["notable_events"].append(
                        {"type": "vision_step", "detail": json.dumps(msg, ensure_ascii=False)[:300]}
                    )
                elif ev == "node_failed":
                    result["notable_events"].append(
                        {"type": "node_failed", "node": nid, "error": msg.get("error")}
                    )
                elif ev in ("run_completed", "run_failed", "run_aborted", "run_completed_with_errors"):
                    result["final_status"] = ev.replace("run_", "")
                    result["error"] = msg.get("error")
                    break
            except asyncio.TimeoutError:
                continue
            except websockets.ConnectionClosed:
                break

    try:
        r = await http.get(f"/api/runs/{run_id}")
        if r.status_code == 200:
            run_body = r.json().get("run") or {}
            if run_body.get("status"):
                result["final_status"] = run_body["status"]
                result["error"] = run_body.get("error")
    except Exception:
        pass

    result["pass"] = result["final_status"] == "completed"
    return result


async def run_workflow_test(http: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    print(f"\n=== Challenge Form Workflow Test ===", flush=True)
    print(f"  page_url={page_url}", flush=True)

    wf_json = build_challenge_workflow(page_url)
    out = await monitor_workflow(http, wf_json)
    out["mode"] = "workflow"
    out["page_url"] = page_url
    print(f"  run_id={out.get('run_id')}", flush=True)
    return out


async def run_autonomous_test(http: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    print(f"\n=== Challenge Form Autonomous Test ===", flush=True)
    body = {
        "objective": (
            "Complete the registration challenge form. "
            "Fill password with SecretPass123, drag the slider verification handle to the "
            "right end until Verified appears, fill name Jane Agent, email jane.agent@example.com, "
            "phone +1 555 0199, then submit. Confirm success panel shows Registration Successful."
        ),
        "start_url": page_url,
        "max_steps": 25,
        "max_seconds": MAX_SECONDS,
        "allowed_domains": ["127.0.0.1", "localhost"],
        "success_criteria": "Success panel visible with submitted values",
        "synthesize_workflow": False,
    }
    r = await http.post("/api/tasks", json=body)
    if r.status_code != 200:
        return {
            "mode": "autonomous",
            "pass": False,
            "error": f"POST /api/tasks HTTP {r.status_code}: {r.text[:300]}",
            "page_url": page_url,
        }
    run_id = r.json()["id"]
    print(f"  run_id={run_id}", flush=True)

    deadline = time.monotonic() + MAX_SECONDS
    result: dict[str, Any] = {
        "mode": "autonomous",
        "run_id": run_id,
        "pass": False,
        "page_url": page_url,
        "final_status": None,
        "error": None,
        "slider_notes": [],
    }
    while time.monotonic() < deadline:
        await asyncio.sleep(3)
        tr = await http.get(f"/api/tasks/{run_id}")
        if tr.status_code != 200:
            continue
        task = tr.json()
        status = task.get("status")
        if status in ("completed", "failed", "aborted"):
            result["final_status"] = status
            result["error"] = task.get("error")
            task_result = task.get("result") or {}
            result["task_result"] = task_result
            result["pass"] = status == "completed" and bool(
                (task_result or {}).get("success")
            )
            break
    else:
        result["final_status"] = "timeout"
    return result


async def run_direct_drag_smoke(page_url: str) -> dict[str, Any]:
    """Playwright smoke: page loads and programmatic drag works."""
    from app.agents.fuzzy import drag_slider
    from app.tools import browser as browser_tools

    print(f"\n=== Direct Drag Smoke (Playwright) ===", flush=True)
    result: dict[str, Any] = {"mode": "direct_drag_smoke", "pass": False, "page_url": page_url}
    try:
        await browser_tools.begin_run(None)
        page = await browser_tools.get_page()
        await page.goto(page_url, wait_until="domcontentloaded")
        drag_out = await drag_slider()
        result["drag_output"] = drag_out
        badge = page.locator("#verify-badge.visible")
        submit_enabled = not await page.locator("#submit-btn").is_disabled()
        result["verified_badge"] = await badge.count() > 0
        result["submit_enabled"] = submit_enabled
        result["pass"] = bool(drag_out.get("dragged")) and submit_enabled
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        await browser_tools.end_run()
    return result


async def main() -> int:
    timeout = httpx.Timeout(60.0, connect=15.0)
    report: dict[str, Any] = {"page_url": PAGE_URL, "results": []}

    async with httpx.AsyncClient(base_url=BASE, timeout=timeout, trust_env=False) as http:
        for _ in range(30):
            try:
                if (await http.get("/api/health")).status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        else:
            print("FAIL: backend not healthy at", BASE, file=sys.stderr)
            return 2

        ok, page_url = await check_page_reachable(http)
        report["page_url"] = page_url
        if not ok:
            print(f"WARN: challenge page not reachable at {PAGE_URL}", flush=True)

        report["results"].append(await run_direct_drag_smoke(page_url))
        await asyncio.sleep(1)
        report["results"].append(await run_workflow_test(http, page_url))

    report_path = Path(__file__).resolve().parents[1] / "challenge_form_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===", flush=True)
    for r in report["results"]:
        status = "PASS" if r.get("pass") else "FAIL"
        print(
            f"  [{status}] {r.get('mode')} run_id={r.get('run_id')} "
            f"final={r.get('final_status')} error={r.get('error')!r}",
            flush=True,
        )
        if r.get("slider_notes"):
            print(f"         slider={r['slider_notes'][:2]}", flush=True)
        if r.get("drag_output"):
            print(f"         drag={json.dumps(r['drag_output'], ensure_ascii=False)[:200]}", flush=True)

    print(f"\nPage URL: {report['page_url']}", flush=True)
    print(f"Report: {report_path}", flush=True)
    return 0 if any(r.get("pass") for r in report["results"]) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
