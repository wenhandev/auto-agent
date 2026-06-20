from __future__ import annotations

from typing import Any

from app.nodes._helpers import eval_field
from app.nodes.result import Item


def _default_out_field(operation: str, field: Any) -> str:
    if field:
        return str(field)
    if operation == "concat":
        return "values"
    return operation


def _numeric(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"non-numeric value for field {field!r}: {value!r}"
        )
    return float(value)


def _empty_result(operation: str, out_field: str) -> Item:
    if operation == "count":
        return Item(json={out_field: 0})
    if operation in ("sum", "avg", "min", "max"):
        return Item(json={out_field: 0})
    if operation == "concat":
        return Item(json={out_field: []})
    if operation == "group_by":
        return Item(json={})
    return Item(json={out_field: None})


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    operation = str(params.get("operation", "count"))
    field = params.get("field")
    out_field = str(
        params.get("out_field")
        or params.get("output_field")
        or _default_out_field(operation, field)
    )
    key_field = params.get("key")

    if not input_items:
        return [_empty_result(operation, out_field)]

    if operation == "count":
        return [Item(json={out_field: len(input_items)})]

    if operation == "concat":
        if not field:
            raise ValueError("concat requires a field")
        values = [
            eval_field(str(field), item, input_items, context) for item in input_items
        ]
        return [Item(json={out_field: values})]

    if operation == "group_by":
        if not key_field:
            raise ValueError("group_by requires a key")
        groups: dict[Any, list[dict[str, Any]]] = {}
        order: list[Any] = []
        for item in input_items:
            k = eval_field(str(key_field), item, input_items, context)
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(dict(item.json))
        return [
            Item(json={str(key_field): k, out_field: groups[k]}) for k in order
        ]

    if not field:
        raise ValueError(f"{operation} requires a field")

    numbers = []
    field_name = str(field)
    for item in input_items:
        raw = eval_field(field_name, item, input_items, context)
        numbers.append(_numeric(raw, field=field_name))

    if operation == "sum":
        value: Any = sum(numbers)
    elif operation == "avg":
        value = sum(numbers) / len(numbers)
    elif operation == "min":
        value = min(numbers)
    elif operation == "max":
        value = max(numbers)
    else:
        raise ValueError(f"unsupported aggregate operation {operation!r}")

    return [Item(json={out_field: value})]
