from __future__ import annotations

from typing import Any

from app.nodes._helpers import eval_field
from app.nodes.result import Item


def _sortable_key(value: Any, *, order: str) -> tuple:
    if value is None:
        return (1, 0)
    group = 0
    try:
        if order == "desc":
            if isinstance(value, (int, float)):
                return (group, -value)
            return (group, value)
        return (group, value)
    except TypeError:
        return (group, str(value))


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    keys = params.get("keys") or []
    items = list(input_items)

    for key_spec in reversed(keys):
        field = key_spec.get("field")
        order = str(key_spec.get("order", "asc"))

        def key_fn(it: Item, *, _field=field, _order=order) -> tuple:
            val = eval_field(_field, it, items, context)
            return _sortable_key(val, order=_order)

        items = sorted(items, key=key_fn)

    return items
