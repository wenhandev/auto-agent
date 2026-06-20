#!/usr/bin/env python3
"""Run auto_agent against the puzzle-gap captcha challenge form (v2).

Usage (backend on :8001):
    python scripts/run_challenge_form_v2_test.py
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
PAGE_URL = f"{BASE}/static/challenge-form-v2.html"
MAX_SECONDS = 180


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def build_v2_workflow(page_url: str, *, action: str = "drag_puzzle") -> dict:
    drag_params: dict[str, Any]
    if action == "drag_slider":
        drag_params = {
            "action": "drag_slider",
            "thumb_selector": "#slider-thumb",
            "track_selector": "#captcha-track",
        }
    else:
        drag_params = {
            "action": "drag_puzzle",
            "thumb_selector": "#slider-thumb",
            "track_selector": "#captcha-track",
            "steps": 32,
            "jitter": True,
        }

    return {
        "nodes": [
            {"id": "start", "type": "start", "label": "开始", "params": {}},
            {
                "id": "nav",
                "type": "navigate",
                "label": "打开拼图挑战表单",
                "params": {"url": page_url},
            },
            {"id": "wait_load", "type": "wait", "label": "等待加载", "params": {"ms": 1000}},
            {
                "id": "fill_pw",
                "type": "fill",
                "label": "填写密码",
                "params": {"selector": "#password", "value": "SecretPass123"},
            },
            {
                "id": "drag_captcha",
                "type": "fuzzy_action",
                "label": "拖动拼图滑块",
                "params": drag_params,
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
            {"id": "wait_success", "type": "wait", "label": "等待成功面板", "params": {"ms": 500}},
            {
                "id": "valid",
                "type": "validation",
                "label": "验证提交成功",
                "params": {
                    "predicate": {
                        "left": "{{= nodes.drag_captcha.output.verified_badge_visible }}",
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
            {"id": "e4", "source": "fill_pw", "target": "drag_captcha"},
            {"id": "e5", "source": "drag_captcha", "target": "fill_name"},
            {"id": "e6", "source": "fill_name", "target": "fill_email"},
            {"id": "e7", "source": "fill_email", "target": "fill_phone"},
            {"id": "e8", "source": "fill_phone", "target": "submit"},
            {"id": "e9", "source": "submit", "target": "wait_success"},
            {"id": "e10", "source": "wait_success", "target": "valid"},
        ],
        "start_id": "start",
    }


async def check_page_reachable(http: httpx.AsyncClient) -> tuple[bool, str]:
    for url in (PAGE_URL, f"http://127.0.0.1:5173/challenge-form-v2.html"):
        try:
            r = await http.get(url)
            if r.status_code == 200 and "滑动拼图验证" in r.text:
                return True, url
        except Exception:
            pass
    return False, PAGE_URL


async def monitor_workflow(http: httpx.AsyncClient, wf_json: dict) -> dict[str, Any]:
    deadline = time.monotonic() + MAX_SECONDS
    result: dict[str, Any] = {
        "run_id": None,
        "pass": False,
        "final_status": None,
        "error": None,
        "node_outputs": {},
        "captcha_notes": [],
        "notable_events": [],
    }

    async with websockets.connect(WS, ping_interval=None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "start", "workflow": wf_json}))
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                ev = msg.get("event")
                nid = msg.get("node_id")
                if ev == "run_started" and msg.get("run_id"):
                    result["run_id"] = msg["run_id"]
                if ev == "node_completed":
                    result["node_outputs"][nid or "?"] = msg.get("output")
                    if nid == "drag_captcha":
                        out = msg.get("output") or {}
                        result["captcha_notes"].append(json.dumps(out, ensure_ascii=False)[:400])
                elif ev == "vision_step":
                    action = msg.get("action") or ""
                    if "drag" in str(action).lower():
                        result["captcha_notes"].append(f"vision_step: {action}")
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


async def run_direct_puzzle_smoke(page_url: str) -> dict[str, Any]:
    from app.agents.fuzzy import drag_puzzle_captcha, drag_slider
    from app.tools import browser as browser_tools

    print("\n=== Direct Puzzle Drag Smoke (Playwright) ===", flush=True)
    result: dict[str, Any] = {"mode": "direct_puzzle_smoke", "pass": False, "page_url": page_url}
    try:
        await browser_tools.begin_run(None)
        page = await browser_tools.get_page()
        await page.goto(page_url, wait_until="domcontentloaded")
        await asyncio.sleep(0.5)

        slider_out = await drag_slider(
            thumb_selector="#slider-thumb",
            track_selector="#captcha-track",
        )
        result["simple_drag_output"] = slider_out

        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(0.5)

        puzzle_out = await drag_puzzle_captcha(steps=32, jitter=True)
        result["puzzle_drag_output"] = puzzle_out
        badge = page.locator("#verify-badge.visible")
        submit_enabled = not await page.locator("#submit-btn").is_disabled()
        result["verified_badge"] = await badge.count() > 0
        result["submit_enabled"] = submit_enabled
        result["pass"] = bool(puzzle_out.get("verified_badge_visible")) and submit_enabled
        result["anti_bot_signal"] = puzzle_out.get("anti_bot_signal")
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        await browser_tools.end_run()
    return result


async def run_simple_drag_workflow(http: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    print("\n=== V2 Simple drag_slider Workflow (expect fail) ===", flush=True)
    wf = build_v2_workflow(page_url, action="drag_slider")
    out = await monitor_workflow(http, wf)
    out["mode"] = "workflow_simple_drag"
    out["page_url"] = page_url
    return out


async def run_puzzle_workflow(http: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    print("\n=== V2 drag_puzzle Workflow ===", flush=True)
    wf = build_v2_workflow(page_url, action="drag_puzzle")
    out = await monitor_workflow(http, wf)
    out["mode"] = "workflow_puzzle_drag"
    out["page_url"] = page_url
    return out


async def run_autonomous_test(http: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    print("\n=== V2 Autonomous Vision Fallback ===", flush=True)
    body = {
        "objective": (
            "Complete the puzzle captcha registration form. "
            "Drag the slider (请拖动滑块完成拼图) to align the puzzle piece with the gap "
            "in the image until 验证成功 appears. Then fill password SecretPass123, "
            "name Jane Agent, email jane.agent@example.com, phone +1 555 0199, and submit."
        ),
        "start_url": page_url,
        "max_steps": 30,
        "max_seconds": MAX_SECONDS,
        "allowed_domains": ["127.0.0.1", "localhost"],
        "success_criteria": "Success panel visible with Registration Successful",
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
        "captcha_notes": [],
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
            result["pass"] = status == "completed" and bool((task_result or {}).get("success"))
            break
    else:
        result["final_status"] = "timeout"
    return result


def build_report_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    puzzle_pass = any(
        r.get("pass") and r.get("mode") in ("direct_puzzle_smoke", "workflow_puzzle_drag")
        for r in results
    )
    simple_blocked = any(
        not r.get("pass")
        and r.get("mode") == "workflow_simple_drag"
        for r in results
    )
    signals: list[str] = []
    for r in results:
        for note in r.get("captcha_notes") or []:
            if "too_fast" in note:
                signals.append("too_fast")
            if "too_linear" in note:
                signals.append("too_linear")
            if "no_jitter" in note:
                signals.append("no_jitter")
            if "misaligned" in note:
                signals.append("misaligned")
        out = r.get("puzzle_drag_output") or r.get("simple_drag_output") or {}
        sig = out.get("anti_bot_signal")
        if sig:
            signals.append(sig)
        node_out = (r.get("node_outputs") or {}).get("drag_captcha") or {}
        sig2 = node_out.get("anti_bot_signal")
        if sig2:
            signals.append(sig2)

    if puzzle_pass:
        verdict = "yes"
    elif any(r.get("pass") for r in results):
        verdict = "partial"
    else:
        verdict = "no"

    return {
        "can_auto_agent_pass": verdict,
        "anti_bot_signals_observed": sorted(set(signals)),
        "simple_drag_blocked_by_antibot": simple_blocked,
    }


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
            print(f"WARN: v2 challenge page not reachable at {PAGE_URL}", flush=True)

        report["results"].append(await run_direct_puzzle_smoke(page_url))
        await asyncio.sleep(1)
        report["results"].append(await run_simple_drag_workflow(http, page_url))
        await asyncio.sleep(1)
        report["results"].append(await run_puzzle_workflow(http, page_url))
        await asyncio.sleep(1)
        report["results"].append(await run_autonomous_test(http, page_url))

    report["summary"] = build_report_summary(report["results"])
    report_path = Path(__file__).resolve().parents[1] / "challenge_form_v2_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== V2 SUMMARY ===", flush=True)
    print(f"  Verdict: {report['summary']['can_auto_agent_pass']}", flush=True)
    print(f"  Anti-bot signals: {report['summary']['anti_bot_signals_observed']}", flush=True)
    for r in report["results"]:
        status = "PASS" if r.get("pass") else "FAIL"
        print(
            f"  [{status}] {r.get('mode')} run_id={r.get('run_id')} "
            f"final={r.get('final_status')} error={r.get('error')!r}",
            flush=True,
        )
        if r.get("captcha_notes"):
            print(f"         notes={r['captcha_notes'][:1]}", flush=True)
        if r.get("puzzle_drag_output"):
            print(
                f"         puzzle={json.dumps(r['puzzle_drag_output'], ensure_ascii=False)[:220]}",
                flush=True,
            )

    print(f"\nPage URL: {report['page_url']}", flush=True)
    print(f"Report: {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
