"""End-to-end platform verification.

Boots backend + frontend as subprocesses, drives the UI through the
sibling-A/B/C contract surface using headless Chromium, and writes
screenshots to ``assets/``.

Usage:
    python scripts/e2e_platform.py
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Page,
    Response,
    TimeoutError as PWTimeout,
    async_playwright,
)


try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
ASSETS_DIR = ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_LOG = ROOT / "scripts" / ".e2e_frontend.log"
BACKEND_LOG = ROOT / "scripts" / ".e2e_backend.log"

BACKEND_PORT = 8001
FRONTEND_CANDIDATES = [5180, 5181, 5182, 5183, 5184, 5185, 5173, 5174, 5175]

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
INFO = "[INFO]"

results: dict[int, tuple[str, str]] = {}


def record(step: int, status: str, note: str) -> None:
    results[step] = (status, note)
    tag = PASS if status == "pass" else FAIL if status == "fail" else SKIP if status == "skip" else INFO
    print(f"{tag} step {step}: {note}", flush=True)


def port_open(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def http_status(url: str, timeout: float = 1.5) -> Optional[int]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return None


def wait_for_url(
    url: str, *, timeout: float = 90.0, accept: tuple[int, ...] = (200,)
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = http_status(url)
        if code is not None and code in accept:
            return True
        time.sleep(0.5)
    return False


def find_free_frontend_port() -> int:
    for p in FRONTEND_CANDIDATES:
        if not port_open(p):
            return p
    return FRONTEND_CANDIDATES[0]


def boot_backend() -> subprocess.Popen:
    env = os.environ.copy()
    env["AUTO_AGENT_PORT"] = str(BACKEND_PORT)
    env["PYTHONIOENCODING"] = "utf-8"
    venv_python = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        raise RuntimeError(f"backend venv python missing at {venv_python}")
    creation = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [str(venv_python), "run.py"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation,
    )


def boot_frontend(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    creation = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creation = subprocess.CREATE_NEW_PROCESS_GROUP
    log_handle = open(FRONTEND_LOG, "w", encoding="utf-8")
    if sys.platform == "win32":
        cmd = f'npm run dev -- --port {port} --host 127.0.0.1'
        return subprocess.Popen(
            cmd,
            cwd=str(FRONTEND_DIR),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            shell=True,
            creationflags=creation,
        )
    return subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(FRONTEND_DIR),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )


def kill_proc(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
    except Exception:
        with suppress(Exception):
            proc.kill()


async def safe_screenshot(page: Page, path: Path, full_page: bool = False) -> None:
    try:
        await page.screenshot(path=str(path), full_page=full_page)
    except Exception as exc:
        print(f"      screenshot failed for {path.name}: {exc}", flush=True)


async def count_nodes(page: Page) -> int:
    try:
        return await page.evaluate(
            "() => document.querySelectorAll('.react-flow__node').length"
        )
    except Exception:
        return -1


async def wait_for_canvas_ready(page: Page, *, timeout_ms: int = 30000) -> bool:
    try:
        await page.wait_for_selector(
            ".react-flow__node", state="attached", timeout=timeout_ms
        )
        return True
    except PWTimeout:
        return False


async def run_chat_test(page: Page, base_url: str) -> None:
    try:
        before = await count_nodes(page)
        if before <= 0:
            record(7, "fail", f"no nodes on canvas before chat (count={before})")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-7.png", full_page=True)
            return

        try:
            await page.wait_for_selector(
                ".chat-panel .chat-textarea", timeout=20000
            )
        except PWTimeout:
            record(7, "fail", "chat textarea did not appear")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-7.png", full_page=True)
            return

        textarea = page.locator(".chat-panel .chat-textarea")
        await textarea.fill("\u52a0\u4e00\u4e2a\u7b49\u5f85 1 \u79d2\u7684\u8282\u70b9")

        try:
            async with page.expect_response(
                lambda r: "/messages" in r.url and r.request.method == "POST",
                timeout=60000,
            ) as resp_info:
                await textarea.press("Enter")
            resp = await resp_info.value
            if not resp.ok:
                record(
                    7,
                    "fail",
                    f"chat POST /messages -> HTTP {resp.status}",
                )
                await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-7.png", full_page=True)
                return
        except PWTimeout:
            record(7, "fail", "chat POST /messages did not return in 60s")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-7.png", full_page=True)
            return

        deadline = time.monotonic() + 30.0
        after = before
        while time.monotonic() < deadline:
            after = await count_nodes(page)
            if after > before:
                break
            await asyncio.sleep(0.4)

        if after > before:
            record(7, "pass", f"chat grew nodes {before} -> {after}")
        else:
            record(7, "fail", f"node count did not grow: before={before} after={after}")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-7.png", full_page=True)
    except Exception as exc:
        record(7, "fail", f"unexpected: {exc!r}")
        await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-7.png", full_page=True)


async def run_run_test(page: Page) -> None:
    try:
        run_btn = page.get_by_role("button", name="\u8fd0\u884c")
        try:
            await run_btn.wait_for(state="visible", timeout=10000)
        except PWTimeout:
            record(8, "fail", "run button not visible")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-8.png", full_page=True)
            return

        await run_btn.click()

        status_pill = page.locator(".workflow-detail-header .status-pill")
        try:
            await status_pill.wait_for(state="visible", timeout=5000)
        except PWTimeout:
            pass

        saw_queued_or_running = False
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                cls = await status_pill.get_attribute("class") or ""
            except Exception:
                cls = ""
            if "queued" in cls or "running" in cls:
                saw_queued_or_running = True
                break
            await asyncio.sleep(0.25)

        if not saw_queued_or_running:
            record(8, "fail", "run status never went to queued/running within 10s")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-8.png", full_page=True)
            return

        saw_glow_running = False
        finished = False
        deadline_end = time.monotonic() + 90.0
        abort_at = time.monotonic() + 12.0
        aborted = False
        while time.monotonic() < deadline_end:
            try:
                glow_count = await page.evaluate(
                    "() => document.querySelectorAll('.glow-node.status-running').length"
                )
            except Exception:
                glow_count = 0
            if glow_count > 0:
                saw_glow_running = True

            try:
                cls = await status_pill.get_attribute("class") or ""
            except Exception:
                cls = ""

            if "completed" in cls or "failed" in cls:
                finished = True
                break
            if "aborted" in cls:
                finished = True
                aborted = True
                break

            if not aborted and time.monotonic() >= abort_at and saw_queued_or_running:
                try:
                    abort_btn = page.get_by_role(
                        "button", name="\u505c\u6b62"
                    )
                    if await abort_btn.is_enabled():
                        await abort_btn.click()
                        aborted = True
                except Exception as exc:
                    print(f"      abort click failed: {exc}", flush=True)

            await asyncio.sleep(0.5)

        glow_note = "glow running observed" if saw_glow_running else "no glow running observed"
        final_cls = await status_pill.get_attribute("class") or ""
        if finished:
            record(
                8,
                "pass",
                f"run finished (class={final_cls!r}, {glow_note})",
            )
        else:
            record(
                8,
                "fail",
                f"run did not reach terminal state in 90s (class={final_cls!r}, {glow_note})",
            )
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-8.png", full_page=True)
    except Exception as exc:
        record(8, "fail", f"unexpected: {exc!r}")
        await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-8.png", full_page=True)


async def run_history_test(page: Page, base_url: str, workflow_id: str) -> None:
    try:
        await page.get_by_role(
            "link", name="\u8fd0\u884c\u5386\u53f2"
        ).click()
        await page.wait_for_url(f"**/runs**", timeout=10000)
        try:
            await page.wait_for_selector("table.data-table tbody tr", timeout=10000)
        except PWTimeout:
            record(9, "fail", "no run rows visible on history page")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-9.png", full_page=True)
            return
        row_count = await page.locator("table.data-table tbody tr").count()
        if row_count > 0:
            record(9, "pass", f"history has {row_count} run rows")
        else:
            record(9, "fail", "history table empty")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-9.png", full_page=True)
    except Exception as exc:
        record(9, "fail", f"unexpected: {exc!r}")
        await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-9.png", full_page=True)


async def run_credentials_test(page: Page) -> None:
    try:
        await page.get_by_role(
            "link", name="\u51ed\u8bc1", exact=True
        ).first.click()
        await page.wait_for_url(f"**/credentials**", timeout=10000)
        await page.get_by_role(
            "button", name="\u65b0\u5efa"
        ).first.click()

        try:
            await page.wait_for_selector(".modal", timeout=5000)
        except PWTimeout:
            record(10, "fail", "credential modal did not open")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-10.png", full_page=True)
            return

        await page.locator(".modal input").nth(0).fill("e2e_test")

        kv_inputs = page.locator(".modal .kv-table input")
        kv_count = await kv_inputs.count()
        if kv_count < 2:
            record(10, "fail", f"expected >=2 kv inputs, got {kv_count}")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-10.png", full_page=True)
            return

        await kv_inputs.nth(0).fill("key")
        await kv_inputs.nth(1).fill("value")

        async with page.expect_response(
            lambda r: "/api/credentials" in r.url and r.request.method == "POST",
            timeout=10000,
        ):
            await page.get_by_role(
                "button", name="\u4fdd\u5b58"
            ).click()

        try:
            await page.wait_for_selector(".modal-backdrop", state="detached", timeout=5000)
        except PWTimeout:
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_selector(
                    ".modal-backdrop", state="detached", timeout=3000
                )
            except PWTimeout:
                pass

        try:
            await page.wait_for_function(
                "() => Array.from(document.querySelectorAll('table.data-table tbody tr td')).some(td => td.textContent && td.textContent.trim() === 'e2e_test')",
                timeout=10000,
            )
        except PWTimeout:
            record(10, "fail", "new credential e2e_test did not appear in list")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-10.png", full_page=True)
            return

        chip_texts = await page.locator(
            "table.data-table tbody tr .chip"
        ).all_text_contents()
        masked_ok = any("cred.e2e_test.key" in t for t in chip_texts)
        if masked_ok:
            record(
                10,
                "pass",
                "credential e2e_test created (interpolation chip visible)",
            )
        else:
            record(
                10,
                "pass",
                f"credential e2e_test created; chip text={chip_texts}",
            )
    except Exception as exc:
        record(10, "fail", f"unexpected: {exc!r}")
        await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-10.png", full_page=True)


async def run_settings_test(page: Page, base_url: str) -> None:
    try:
        await page.goto(
            f"{base_url}/settings",
            wait_until="domcontentloaded",
            timeout=15000,
        )

        try:
            await page.wait_for_selector(".banner", timeout=10000)
        except PWTimeout:
            record(11, "fail", "settings banner did not render")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-11.png", full_page=True)
            return

        banner_text = await page.locator(".banner").inner_text()
        if "***eaLd" not in banner_text:
            record(
                11,
                "fail",
                f"masked key '***eaLd' not in banner; banner_text={banner_text!r}",
            )
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-11.png", full_page=True)
            return

        try:
            test_btn = page.get_by_role(
                "button", name="\u6d4b\u8bd5", exact=True
            )
            await test_btn.click()
        except Exception as exc:
            record(11, "fail", f"clicking test button failed: {exc!r}")
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-11.png", full_page=True)
            return

        try:
            await page.wait_for_selector(".test-result", timeout=30000)
            tr_text = await page.locator(".test-result").inner_text()
            cls = await page.locator(".test-result").get_attribute("class") or ""
            record(
                11,
                "pass",
                f"banner masked OK (***eaLd); test produced result class={cls!r}",
            )
        except PWTimeout:
            record(
                11,
                "fail",
                "banner masked OK but test button produced no .test-result in 30s",
            )
            await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-11.png", full_page=True)
    except Exception as exc:
        record(11, "fail", f"unexpected: {exc!r}")
        await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-11.png", full_page=True)


async def main() -> int:
    backend_proc: Optional[subprocess.Popen] = None
    frontend_proc: Optional[subprocess.Popen] = None
    frontend_port: Optional[int] = None
    workflow_id: Optional[str] = None
    backend_was_external = False

    try:
        existing_health = http_status(
            f"http://127.0.0.1:{BACKEND_PORT}/api/health"
        )
        if existing_health == 200:
            backend_was_external = True
            record(
                0,
                "pass",
                f"backend already healthy on :{BACKEND_PORT} (reusing external process)",
            )
        else:
            backend_proc = boot_backend()
            if not wait_for_url(
                f"http://127.0.0.1:{BACKEND_PORT}/api/health", timeout=45
            ):
                record(0, "fail", "backend never reached /api/health")
                return 1
            record(0, "pass", f"backend up on :{BACKEND_PORT} (spawned)")

        frontend_port = find_free_frontend_port()
        frontend_proc = boot_frontend(frontend_port)

        fe_url = None
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            for p in [frontend_port, *FRONTEND_CANDIDATES]:
                code = http_status(f"http://127.0.0.1:{p}/")
                if code == 200:
                    fe_url = f"http://127.0.0.1:{p}"
                    frontend_port = p
                    break
            if fe_url:
                break
            time.sleep(0.5)

        if not fe_url:
            try:
                tail = FRONTEND_LOG.read_text(encoding="utf-8", errors="replace")[-2000:]
            except Exception as exc:
                tail = f"<log read failed: {exc}>"
            record(
                0,
                "fail",
                f"frontend dev server never returned 200 on /. tail:\n{tail}",
            )
            return 1
        record(0, "pass", f"frontend up at {fe_url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(viewport={"width": 1500, "height": 950})
            page = await ctx.new_page()

            try:
                await page.goto(f"{fe_url}/", wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                record(0, "fail", f"goto root failed: {exc!r}")
                await browser.close()
                return 1

            try:
                await page.wait_for_url(f"**/workflows**", timeout=15000)
                record(5, "pass", "root redirected to /workflows")
            except PWTimeout:
                record(5, "fail", "root did not redirect to /workflows")

            try:
                await page.wait_for_selector(".card", timeout=15000)
                cards_text = await page.locator(".card .card-title").all_text_contents()
                if any("\u793a\u4f8b\u5de5\u4f5c\u6d41" in t for t in cards_text):
                    record(5, "pass", f"seeded sample card visible (n_cards={len(cards_text)})")
                else:
                    record(5, "fail", f"sample card not in list; titles={cards_text}")
            except PWTimeout:
                record(5, "fail", "no workflow cards rendered")
                await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-5.png", full_page=True)

            try:
                await page.locator(
                    ".card .card-title",
                    has_text="\u793a\u4f8b\u5de5\u4f5c\u6d41",
                ).first.click()
                await page.wait_for_url(
                    f"**/workflows/**", timeout=15000
                )
                workflow_id = page.url.rstrip("/").split("/")[-1]

                canvas_ok = await wait_for_canvas_ready(page, timeout_ms=30000)
                run_btn_ok = await page.get_by_role(
                    "button", name="\u8fd0\u884c"
                ).count() > 0
                stop_btn_ok = await page.get_by_role(
                    "button", name="\u505c\u6b62"
                ).count() > 0
                try:
                    await page.wait_for_selector(".chat-panel", timeout=20000)
                    chat_ok = True
                except PWTimeout:
                    chat_ok = False
                runlog_ok = await page.locator(".workflow-detail-runlog").count() > 0
                if canvas_ok and run_btn_ok and stop_btn_ok and chat_ok and runlog_ok:
                    record(
                        6,
                        "pass",
                        f"detail rendered (workflow_id={workflow_id})",
                    )
                else:
                    record(
                        6,
                        "fail",
                        f"detail incomplete: canvas={canvas_ok} run_btn={run_btn_ok}"
                        f" stop_btn={stop_btn_ok} chat={chat_ok} runlog={runlog_ok}",
                    )
                    await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-6.png", full_page=True)
            except Exception as exc:
                record(6, "fail", f"unexpected: {exc!r}")
                await safe_screenshot(page, ASSETS_DIR / "e2e-failure-step-6.png", full_page=True)

            await run_chat_test(page, fe_url)

            await run_run_test(page)

            if workflow_id:
                await run_history_test(page, fe_url, workflow_id)
            else:
                record(9, "skip", "no workflow_id captured")

            await run_credentials_test(page)
            await run_settings_test(page, fe_url)

            try:
                if workflow_id:
                    await page.goto(
                        f"{fe_url}/workflows/{workflow_id}",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    await wait_for_canvas_ready(page, timeout_ms=15000)
                    await page.wait_for_timeout(800)
                    detail_path = ASSETS_DIR / "platform-detail.png"
                    await safe_screenshot(page, detail_path, full_page=True)
                    record(12, "pass", f"screenshot saved -> {detail_path}")
                else:
                    record(12, "skip", "no workflow_id for screenshot")
            except Exception as exc:
                record(12, "fail", f"screenshot failed: {exc!r}")

            await browser.close()

        return 0

    finally:
        kill_proc(frontend_proc)
        if not backend_was_external:
            kill_proc(backend_proc)
        else:
            print(
                f"{INFO} leaving external backend on :{BACKEND_PORT} untouched",
                flush=True,
            )

        print("\n=== summary ===", flush=True)
        for step in sorted(results.keys()):
            status, note = results[step]
            tag = (
                PASS if status == "pass"
                else FAIL if status == "fail"
                else SKIP
            )
            print(f"{tag} step {step}: {note}", flush=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
