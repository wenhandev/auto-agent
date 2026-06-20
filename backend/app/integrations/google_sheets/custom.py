from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.integrations.auth import RenderedRequest
from app.integrations.schema import Operation


def _build_a1_range(*, sheet: str, range_a1: str) -> str:
    sheet = sheet.strip()
    range_a1 = range_a1.strip()
    if sheet and range_a1:
        if "!" in range_a1:
            return range_a1
        return f"{sheet}!{range_a1}"
    if sheet:
        return sheet
    return range_a1


def _rows_to_objects(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values:
        return []
    headers = [str(h) for h in values[0]]
    out: list[dict[str, Any]] = []
    for row in values[1:]:
        obj: dict[str, Any] = {}
        for idx, header in enumerate(headers):
            obj[header] = row[idx] if idx < len(row) else None
        out.append(obj)
    return out


async def before_request(
    app: str,
    resource: str,
    operation: str,
    req: RenderedRequest,
    fields: dict[str, Any],
) -> None:
    if resource != "values" or operation not in ("get", "append", "update", "clear"):
        return
    sheet = str(fields.get("sheet", "") or "")
    range_a1 = str(fields.get("range", "") or "")
    if not sheet and not range_a1:
        return
    built = _build_a1_range(sheet=sheet, range_a1=range_a1)
    spreadsheet_id = str(fields.get("spreadsheet_id", ""))
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(spreadsheet_id, safe='')}/values/{quote(built, safe='')}"
    if operation == "append":
        req.url = f"{base}:append"
    elif operation == "clear":
        req.url = f"{base}:clear"
    else:
        req.url = base


def map_items(
    app: str,
    resource: str,
    operation: str,
    http_out: dict[str, Any],
    op: Operation,
    fields: dict[str, Any],
    default_items: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    if resource != "values" or operation != "get":
        return None
    if not fields.get("as_objects"):
        return default_items
    payload = http_out.get("json") or {}
    values = payload.get("values")
    if not isinstance(values, list):
        return default_items
    return _rows_to_objects(values)


__all__ = ["before_request", "map_items"]
