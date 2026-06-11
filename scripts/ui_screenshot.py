"""Drive the UI through one workflow run and snapshot the result panel.

Usage:
    python scripts/ui_screenshot.py [URL]
    URL defaults to http://localhost:5176/  (Vite picked 5176 in this session)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


PROMPT = "打开 https://example.com 然后提取页面 H1 文字"
OUT_PATH = (
    Path(__file__).resolve().parents[1] / "assets" / "result-demo.png"
)


async def main(url: str) -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto(url)
        await page.wait_for_selector("textarea", timeout=15000)
        await page.fill("textarea", PROMPT)

        async with page.expect_response(
            lambda r: r.url.endswith("/api/workflow/generate")
            and r.request.method == "POST",
            timeout=120_000,
        ) as resp_info:
            await page.get_by_role("button", name="生成工作流").click()
        await resp_info.value
        await page.wait_for_function(
            "(() => {"
            " const btn = [...document.querySelectorAll('button')]"
            "   .find(b => b.textContent && b.textContent.includes('生成工作流'));"
            " return btn && !btn.disabled;"
            "})()",
            timeout=10_000,
        )

        await page.get_by_role("button", name="运行").click()
        await page.wait_for_function(
            "document.querySelector('.result-panel') !== null",
            timeout=180_000,
        )
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUT_PATH))
        await browser.close()
    print(f"saved {OUT_PATH}")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5176/"
    sys.exit(asyncio.run(main(target)))
