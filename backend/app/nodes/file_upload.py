from __future__ import annotations

from pathlib import Path
from typing import Any

from app.tools.browser import get_page
from app.tools.sandbox import SandboxViolation, resolve_sandbox_path


async def _resolve_selector(target: str | None) -> str:
    if target and str(target).strip():
        return str(target).strip()

    from app.agents.selector_finder import propose_selector

    page = await get_page()
    result = await propose_selector(
        page=page,
        instruction="Find the file input element to upload a file.",
        mode="dom",
    )
    selector = result.get("selector")
    if not selector or not str(selector).strip():
        raise RuntimeError("could not locate file input (no selector and vision find failed)")
    return str(selector).strip()


async def run(
    params: dict[str, Any],
    *,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    if workflow_id is None:
        raise SandboxViolation("file_upload requires a persisted workflow")

    file_ref = str(params["file"])
    resolved = resolve_sandbox_path(file_ref, workflow_id=workflow_id)
    if not resolved.is_file():
        raise FileNotFoundError(f"file not found: {file_ref}")

    selector = await _resolve_selector(params.get("target"))
    page = await get_page()
    await page.locator(selector).set_input_files(str(resolved))
    return {
        "selector": selector,
        "file": file_ref,
        "filename": Path(file_ref).name,
        "uploaded": True,
    }
