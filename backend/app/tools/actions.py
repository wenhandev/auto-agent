from __future__ import annotations

import asyncio

from app.agents.extractor import extract_from_page
from app.tools.browser import get_page


async def navigate(url: str) -> dict:
    page = await get_page()
    await page.goto(url)
    return {"url": page.url, "title": await page.title()}


async def click(selector: str) -> dict:
    page = await get_page()
    await page.click(selector)
    return {"selector": selector, "clicked": True}


async def fill(selector: str, value: str) -> dict:
    page = await get_page()
    await page.fill(selector, value)
    return {"selector": selector, "value": value}


async def wait(ms: int) -> dict:
    await asyncio.sleep(ms / 1000)
    return {"waited_ms": ms}


async def screenshot() -> bytes:
    page = await get_page()
    return await page.screenshot(full_page=False)


async def extract(instruction: str) -> dict:
    page = await get_page()
    return await extract_from_page(page, instruction)
