from __future__ import annotations

from typing import Any

from app.nodes._artifact_store import store_download_bytes
from app.tools.browser import get_page


async def _render_pdf(page: Any) -> bytes:
    try:
        return await page.pdf()
    except Exception:
        cdp = await page.context.new_cdp_session(page)
        result = await cdp.send(
            "Page.printToPDF",
            {"printBackground": True, "preferCSSPageSize": True},
        )
        import base64

        return base64.b64decode(result["data"])


async def run(
    params: dict[str, Any],
    *,
    node_id: str | None = None,
) -> dict[str, Any]:
    page = await get_page()
    pdf_bytes = await _render_pdf(page)
    filename = str(params.get("filename") or "page.pdf")
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    stored = store_download_bytes(pdf_bytes, filename=filename, node_id=node_id)
    return stored
