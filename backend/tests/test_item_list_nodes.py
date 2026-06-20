from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes import aggregate, filter as filter_node
from app.nodes import limit as limit_node
from app.nodes import remove_duplicates, sort, split_out
from app.nodes.result import Item
from app.services.expressions import ExpressionError


def _items(payloads: list[dict]) -> list[Item]:
    return [Item(json=p) for p in payloads]


async def _run_filter(params: dict, items: list[Item]) -> list[Item]:
    return await filter_node.run(params, input_items=items, context={})


async def _run_sort(params: dict, items: list[Item]) -> list[Item]:
    return await sort.run(params, input_items=items, context={})


async def _run_limit(params: dict, items: list[Item]) -> list[Item]:
    return await limit_node.run(params, input_items=items, context={})


async def _run_aggregate(params: dict, items: list[Item]) -> list[Item]:
    return await aggregate.run(params, input_items=items, context={})


async def _run_split_out(params: dict, items: list[Item]) -> list[Item]:
    return await split_out.run(params, input_items=items, context={})


async def _run_dedupe(params: dict, items: list[Item]) -> list[Item]:
    return await remove_duplicates.run(params, input_items=items, context={})


def test_filter_keep_matching():
    items = _items([{"in": True}, {"in": False}, {"in": True}])
    out = asyncio.run(_run_filter({"predicate": "{{= item.json['in'] }}"}, items))
    assert [it.json for it in out] == [{"in": True}, {"in": True}]


def test_filter_empty_result():
    items = _items([{"in": False}])
    out = asyncio.run(_run_filter({"predicate": "{{= item.json['in'] }}"}, items))
    assert out == []


def test_filter_predicate_error_includes_index():
    items = _items([{"x": 1}, {"x": "bad"}])
    predicate = "{{= 1/0 if item.json.x == 'bad' else True }}"
    with pytest.raises(ExpressionError, match="item index 1"):
        asyncio.run(_run_filter({"predicate": predicate}, items))


def test_sort_descending():
    items = _items([{"price": 10}, {"price": 30}, {"price": 20}])
    out = asyncio.run(
        _run_sort({"keys": [{"field": "price", "order": "desc"}]}, items)
    )
    assert [it.json["price"] for it in out] == [30, 20, 10]


def test_sort_none_last():
    items = _items([{"v": 2}, {"v": None}, {"v": 1}])
    out = asyncio.run(
        _run_sort({"keys": [{"field": "v", "order": "asc"}]}, items)
    )
    assert [it.json["v"] for it in out] == [1, 2, None]


def test_limit_first_n():
    items = _items([{"i": i} for i in range(7)])
    out = asyncio.run(_run_limit({"keep": "first", "count": 5}, items))
    assert len(out) == 5
    assert [it.json["i"] for it in out] == [0, 1, 2, 3, 4]


def test_limit_last_n():
    items = _items([{"i": i} for i in range(7)])
    out = asyncio.run(_run_limit({"keep": "last", "count": 3}, items))
    assert [it.json["i"] for it in out] == [4, 5, 6]


def test_aggregate_sum():
    items = _items([{"amount": 10}, {"amount": 20}, {"amount": 30}])
    out = asyncio.run(
        _run_aggregate({"operation": "sum", "field": "amount", "out_field": "amount"}, items)
    )
    assert len(out) == 1
    assert out[0].json["amount"] == 60


def test_aggregate_group_by():
    items = _items([{"c": "a", "v": 1}, {"c": "b", "v": 2}, {"c": "a", "v": 3}])
    out = asyncio.run(
        _run_aggregate(
            {"operation": "group_by", "key": "c", "out_field": "rows"},
            items,
        )
    )
    by_key = {it.json["c"]: it.json["rows"] for it in out}
    assert by_key["a"] == [{"c": "a", "v": 1}, {"c": "a", "v": 3}]
    assert by_key["b"] == [{"c": "b", "v": 2}]


def test_aggregate_sum_non_numeric_fails():
    items = _items([{"name": "abc"}])
    with pytest.raises(ValueError, match="non-numeric value for field 'name': 'abc'"):
        asyncio.run(_run_aggregate({"operation": "sum", "field": "name"}, items))


def test_aggregate_empty_input_identities():
    assert asyncio.run(_run_aggregate({"operation": "count"}, []))[0].json["count"] == 0
    assert (
        asyncio.run(_run_aggregate({"operation": "sum", "field": "x", "out_field": "sum"}, []))[0].json["sum"]
        == 0
    )
    assert asyncio.run(_run_aggregate({"operation": "concat", "field": "x"}, []))[0].json["x"] == []


def test_split_out_explode():
    items = [Item(json={"id": 1, "tags": ["x", "y"]})]
    out = asyncio.run(
        _run_split_out(
            {"field": "tags", "out_field": "tag", "include_other_fields": True},
            items,
        )
    )
    assert [it.json for it in out] == [
        {"id": 1, "tag": "x"},
        {"id": 1, "tag": "y"},
    ]


def test_remove_duplicates_selected_fields():
    items = _items([{"id": 1}, {"id": 2}, {"id": 1}])
    out = asyncio.run(
        _run_dedupe(
            {"compare": "selected_fields", "fields": ["id"]},
            items,
        )
    )
    assert [it.json for it in out] == [{"id": 1}, {"id": 2}]
