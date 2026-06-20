#!/usr/bin/env python3
"""Manual smoke test for the Acme Supply Hub demo portal via Playwright.

Usage (backend on :8000):
    python scripts/run_demo_portal_smoke.py

Requires: playwright installed in backend venv (already a project dependency).
"""
from __future__ import annotations

import asyncio
import os
import sys

PORT = os.environ.get("AUTO_AGENT_PORT", "8000")
BASE = f"http://127.0.0.1:{PORT}"
PAGE_URL = f"{BASE}/demo"


async def main() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright not installed — run: pip install playwright && playwright install chromium")
        return 1

    print(f"[smoke] Opening {PAGE_URL}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(PAGE_URL, wait_until="networkidle")

        # Login step 1
        await page.fill('[data-testid="login-email"]', "demo@acme.com")
        await page.fill('[data-testid="login-password"]', "demo1234")
        await page.click('[data-testid="login-submit"]')
        await page.wait_for_selector('[data-testid="otp-form"]:not(.hidden)', timeout=5000)

        # OTP step 2
        await page.fill('[data-testid="otp-code"]', "123456")
        await page.click('[data-testid="otp-submit"]')
        await page.wait_for_selector('[data-testid="app-view"]:not(.hidden)', timeout=5000)
        print("[smoke] Login OK")

        # Navigate to Orders
        await page.click('[data-testid="nav-orders"]')
        await page.wait_for_selector('[data-testid="page-orders"]:not(.hidden)')
        print("[smoke] Orders page OK")

        # Filter and select order
        await page.fill('[data-testid="filter-order-id"]', "8842")
        await page.click('[data-testid="filter-submit"]')
        await page.click('[data-testid="order-row-PO-2024-8842"]')
        await page.wait_for_selector('[data-testid="order-json"]', timeout=5000)
        order_json = await page.inner_text('[data-testid="order-json"]')
        assert "PO-2024-8842" in order_json
        assert "lineItems" in order_json
        print("[smoke] Order detail JSON OK")

        # Invoices
        await page.click('[data-testid="nav-invoices"]')
        await page.click('[data-testid="download-summary-INV-2024-3325"]')
        await page.wait_for_selector('[data-testid="invoice-json"]', timeout=5000)
        invoice_json = await page.inner_text('[data-testid="invoice-json"]')
        assert "INV-2024-3325" in invoice_json
        print("[smoke] Invoice summary JSON OK")

        # Shipments expand
        await page.click('[data-testid="nav-shipments"]')
        await page.click('[data-testid="shipment-toggle-SHP-2024-4388"]')
        await page.wait_for_selector('[data-testid="shipment-timeline-SHP-2024-4388"]:not(.hidden)')
        print("[smoke] Shipment timeline expand OK")

        await browser.close()

    print("[smoke] All checks passed")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(asyncio.run(main()))
