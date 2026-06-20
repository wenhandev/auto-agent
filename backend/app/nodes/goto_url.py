from __future__ import annotations

from typing import Any, Literal

from app.tools.browser import get_page

WaitUntil = Literal["load", "domcontentloaded", "networkidle", "commit"]


async def run(params: dict[str, Any]) -> dict[str, Any]:
    url = str(params["url"])
    wait_until = str(params.get("wait_until", "load"))
    page = await get_page()
    await page.goto(url, wait_until=wait_until)
    return {"url": page.url, "title": await page.title()}
