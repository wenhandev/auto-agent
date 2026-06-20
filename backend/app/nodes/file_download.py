from __future__ import annotations

from pathlib import Path
from typing import Any

from app.nodes._artifact_store import store_download_bytes
from app.tools.browser import get_page


async def _resolve_selector(target: str | None) -> str:
    if target and str(target).strip():
        return str(target).strip()

    from app.agents.selector_finder import propose_selector

    page = await get_page()
    result = await propose_selector(
        page=page,
        instruction="Find the element that triggers a file download.",
        mode="dom",
    )
    selector = result.get("selector")
    if not selector or not str(selector).strip():
        raise RuntimeError(
            "could not locate download trigger (no selector and vision find failed)"
        )
    return str(selector).strip()


async def run(
    params: dict[str, Any],
    *,
    node_id: str | None = None,
) -> dict[str, Any]:
    timeout_ms = int(params.get("timeout_ms", 30_000))
    selector = await _resolve_selector(params.get("target"))
    page = await get_page()

    async with page.expect_download(timeout=timeout_ms) as download_info:
        await page.locator(selector).click()
    download = await download_info.value
    path = await download.path()
    if path is None:
        raise RuntimeError("download did not produce a file path")
    data = Path(path).read_bytes()

    filename = download.suggested_filename or "download.bin"
    stored = store_download_bytes(data, filename=filename, node_id=node_id)
    return stored
