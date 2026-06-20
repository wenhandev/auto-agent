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
    raw = params.get("input")
    if raw is None:
        raise ValueError("parse_json requires params.input")
    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"parse_json: invalid JSON: {exc}") from exc
    return [Item(json={"parsed": parsed})]
