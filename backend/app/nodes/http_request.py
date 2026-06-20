from __future__ import annotations

from typing import Any

from app.nodes._http_client import request
from app.nodes.result import Item


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
    transport: Any = None,
) -> list[Item]:
    method = str(params.get("method", "GET"))
    url = str(params["url"])
    headers = params.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be a dict")
    body = params.get("body")
    body_kind = str(params.get("body_kind", "json"))
    timeout_ms = int(params.get("timeout_ms", 15_000))

    output = await request(
        method=method,
        url=url,
        headers={str(k): str(v) for k, v in headers.items()},
        body=body,
        body_kind=body_kind,
        timeout_ms=timeout_ms,
        transport=transport,
    )
    return [Item(json=output)]
