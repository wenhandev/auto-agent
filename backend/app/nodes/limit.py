from __future__ import annotations

from typing import Any

from app.nodes.result import Item


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    keep = str(params.get("keep", "first"))
    count = max(0, int(params.get("count", 0)))
    if keep == "last":
        return list(input_items[-count:]) if count else []
    return list(input_items[:count])
