from __future__ import annotations

import json
from typing import Any

from app.nodes.result import Item


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    compare = str(params.get("compare", "selected_fields"))
    fields = params.get("fields") or []

    seen: set[Any] = set()
    out: list[Item] = []
    for item in input_items:
        if compare == "all_fields":
            key: Any = json.dumps(item.json, sort_keys=True, default=str)
        else:
            key = tuple(item.json.get(str(f)) for f in fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
