from __future__ import annotations

import csv
import io
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
        raise ValueError("parse_csv requires params.input")
    text = str(raw)
    has_header = bool(params.get("has_header", True))
    delimiter = str(params.get("delimiter", ","))

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows_raw = list(reader)
    if not rows_raw:
        return [Item(json={"rows": [], "header": [] if has_header else None})]

    if has_header:
        header = rows_raw[0]
        rows = [dict(zip(header, row, strict=False)) for row in rows_raw[1:]]
        return [Item(json={"rows": rows, "header": header})]

    return [Item(json={"rows": rows_raw, "header": None})]
