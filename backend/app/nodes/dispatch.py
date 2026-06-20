"""Dispatch table for data-transform node modules."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from app.nodes import (
    aggregate,
    datetime,
    filter,
    limit,
    remove_duplicates,
    rename_keys,
    set as set_node,
    sort,
    split_out,
)
from app.nodes.result import Item

TransformRun = Callable[..., Awaitable[list[Item]]]

_HANDLERS: dict[str, TransformRun] = {
    "set": set_node.run,
    "rename_keys": rename_keys.run,
    "datetime": datetime.run,
    "filter": filter.run,
    "sort": sort.run,
    "limit": limit.run,
    "aggregate": aggregate.run,
    "split_out": split_out.run,
    "remove_duplicates": remove_duplicates.run,
}

TRANSFORM_NODE_TYPES = frozenset(_HANDLERS.keys())


async def run_transform(
    node_type: str,
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    handler = _HANDLERS.get(node_type)
    if handler is None:
        raise ValueError(f"unknown transform node type: {node_type!r}")
    return await handler(params, input_items=input_items, context=context)


__all__ = ["TRANSFORM_NODE_TYPES", "run_transform"]
