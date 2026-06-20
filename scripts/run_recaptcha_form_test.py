#!/usr/bin/env python3
"""Run auto_agent against the local Google reCAPTCHA v2 test form.

Usage (backend on :8001):
    python scripts/run_recaptcha_form_test.py
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
PAGE_URL = f"{BASE}/static/recaptcha-form.html"
MAX_SECONDS = 180


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def build_recaptcha_workflow(page_url: str) -> dict:
    """Deterministic fills + iframe reCAPTCHA click + submit + validation."""
    return {
        "nodes": [
            {"id": "start", "type": "start", "label": "开始", "params": {}},
            {
                "id": "nav",
                "type": "navigate",
                "label": "打开 reCAPTCHA 表单",
                "params": {"url": page_url},
            },
            {
                "id": "wait_load",
                "type": "wait",
                "label": "等待加载",
                "params": {"ms": 5000},
            },
            {
                "id": "fill_pw",
                "type": "fill",
                "label": "填写密码",
                "params": {"selector": "#password", "value": "SecretPass123"},
            },
            {
                "id": "click_captcha",
                "type": "fuzzy_action",
                "label": "点击 reCAPTCHA",
                "params": {"action": "click_recaptcha"},
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
                "params": {"ms": 3000},
            },
            {
                "id": "valid",
                "type": "validation",
                "label": "验证 reCAPTCHA 已点击",
                "params": {
                    "predicate": {
                        "left": "{{= nodes.click_captcha.output.clicked }}",
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
            {"id": "e4", "source": "fill_pw", "target": "click_captcha"},
            {"id": "e5", "source": "click_captcha", "target": "fill_name"},
            {"id": "e6", "source": "fill_name", "target": "fill_email"},
            {"id": "e7", "source": "fill_email", "target": "fill_phone"},
            {"id": "e8", "source": "fill_phone", "target": "submit"},
            {"id": "e9", "source": "submit", "target": "wait_success"},
            {"id": "e10", "source": "wait_success", "target": "valid"},
        ],
        "start_id": "start",
    }


def build_vision_fallback_workflow(page_url: str) -> dict:
    """Fallback workflow using vision_navigate if iframe click fails."""
    wf = build_recaptcha_workflow(page_url)
    wf["nodes"][4] = {
        "id": "click_captcha",
        "type": "fuzzy_action",
        "label": "点击 reCAPTCHA (vision)",
        "params": {
            "instruction": (
                "Click the 'I'm not a robot' reCAPTCHA checkbox. "
                "Wait until the checkbox shows a check mark and the token is filled."
            ),
            "max_steps": 6,
        },
    }
    return wf


async def check_page_reachable(http: httpx.AsyncClient) -> tuple[bool, str]:
    for url in (PAGE_URL, f"http://127.0.0.1:5173/recaptcha-form.html"):
        try:
            r = await http.get(url)
            if r.status_code == 200 and "Secure Registration" in r.text:
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
                    if nid == "click_captcha":
                        out = msg.get("output") or {}
                        result["captcha_notes"].append(json.dumps(out, ensure_ascii=False)[:400])
                elif ev == "vision_step":
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

    captcha_out = result["node_outputs"].get("click_captcha") or {}
    success_visible = False
    try:
        # workflow pass if run completed; also track captcha click outcome
        success_visible = bool(captcha_out.get("token_present") or captcha_out.get("checkbox_checked"))
    except Exception:
        pass
    result["captcha_token_present"] = bool(captcha_out.get("token_present"))
    result["captcha_clicked"] = bool(captcha_out.get("clicked"))
    result["pass"] = result["final_status"] == "completed"
    result["captcha_success"] = success_visible
    return result


async def run_direct_recaptcha_smoke(page_url: str) -> dict[str, Any]:
    """Playwright smoke: load page, click reCAPTCHA iframe, fill and submit."""
    from playwright.async_api import async_playwright

    from app.agents.fuzzy import _click_recaptcha_in_page

    print(f"\n=== Direct reCAPTCHA Smoke (Playwright) ===", flush=True)
    result: dict[str, Any] = {"mode": "direct_recaptcha_smoke", "pass": False, "page_url": page_url}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(page_url, wait_until="load", timeout=60000)
            await page.wait_for_timeout(5000)

            click_out = await _click_recaptcha_in_page(page)
            result["click_output"] = click_out

            await page.fill("#password", "SecretPass123")
            await page.fill("#name", "Jane Agent")
            await page.fill("#email", "jane.agent@example.com")
            await page.fill("#phone", "+1 555 0199")

            submit_enabled = not await page.locator("#submit-btn").is_disabled()
            result["submit_enabled_before_click"] = submit_enabled

            if click_out.get("token_present"):
                await page.click("#submit-btn")
                await page.wait_for_timeout(3500)
                success = await page.locator("#success-panel.visible").count() > 0
                result["success_panel_visible"] = success
                result["pass"] = success
            else:
                result["success_panel_visible"] = False
                result["pass"] = False
                result["error"] = click_out.get("error") or "reCAPTCHA token not obtained after click"
            await browser.close()
    except Exception as exc:
        result["error"] = str(exc)
    return result


async def run_workflow_test(http: httpx.AsyncClient, page_url: str) -> dict[str, Any]:
    print(f"\n=== reCAPTCHA Workflow Test ===", flush=True)
    print(f"  page_url={page_url}", flush=True)

    wf_json = build_recaptcha_workflow(page_url)
    out = await monitor_workflow(http, wf_json)
    out["mode"] = "workflow"
    out["page_url"] = page_url
    print(f"  run_id={out.get('run_id')}", flush=True)
    return out


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
            print(f"WARN: reCAPTCHA page not reachable at {PAGE_URL}", flush=True)

        report["results"].append(await run_direct_recaptcha_smoke(page_url))
        await asyncio.sleep(1)
        report["results"].append(await run_workflow_test(http, page_url))

    report_path = Path(__file__).resolve().parents[1] / "recaptcha_form_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== SUMMARY ===", flush=True)
    for r in report["results"]:
        status = "PASS" if r.get("pass") else "FAIL"
        print(
            f"  [{status}] {r.get('mode')} run_id={r.get('run_id')} "
            f"final={r.get('final_status')} error={r.get('error')!r}",
            flush=True,
        )
        if r.get("captcha_notes"):
            print(f"         captcha={r['captcha_notes'][:2]}", flush=True)
        if r.get("click_output"):
            print(
                f"         click={json.dumps(r['click_output'], ensure_ascii=False)[:250]}",
                flush=True,
            )
        if "captcha_token_present" in r:
            print(
                f"         token_present={r.get('captcha_token_present')} "
                f"clicked={r.get('captcha_clicked')}",
                flush=True,
            )

    print(f"\nPage URL: {report['page_url']}", flush=True)
    print(f"Report: {report_path}", flush=True)
    print(
        "\nNote: Google test keys always pass siteverify but may still show image "
        "challenges in production keys. Test keys are intended for automated testing.",
        flush=True,
    )
    return 0 if any(r.get("pass") for r in report["results"]) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
