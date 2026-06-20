from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes import datetime as datetime_node
from app.nodes import rename_keys, set
from app.nodes.result import Item, NodeResult


async def _run_set(params: dict, items: list[Item]) -> list[Item]:
    return await set.run(params, input_items=items, context={})


async def _run_rename(params: dict, items: list[Item]) -> list[Item]:
    return await rename_keys.run(params, input_items=items, context={})


async def _run_datetime(params: dict, items: list[Item]) -> list[Item]:
    return await datetime_node.run(params, input_items=items, context={})


def test_set_computed_assignment():
    items = [Item(json={"qty": 3, "price": 10})]
    params = {
        "assignments": [
            {"name": "total", "value": "{{= item.json.qty * item.json.price }}"},
        ],
    }
    out = asyncio.run(_run_set(params, items))
    assert out[0].json == {"qty": 3, "price": 10, "total": 30}


def test_set_keep_only_set():
    items = [Item(json={"id": 7, "junk": 1})]
    params = {
        "keep_only_set": True,
        "assignments": [{"name": "id", "value": "{{= item.json.id }}"}],
    }
    out = asyncio.run(_run_set(params, items))
    assert out[0].json == {"id": 7}


def test_set_remove_field():
    items = [Item(json={"id": 1, "secret": "x"})]
    params = {"fields_to_remove": ["secret"]}
    out = asyncio.run(_run_set(params, items))
    assert out[0].json == {"id": 1}


def test_rename_keys_simple():
    items = [Item(json={"old": 5})]
    params = {"pairs": [{"from": "old", "to": "new"}]}
    out = asyncio.run(_run_rename(params, items))
    assert out[0].json == {"new": 5}


def test_rename_keys_collision_error():
    items = [Item(json={"a": 1, "b": 2})]
    params = {
        "pairs": [{"from": "a", "to": "b"}],
        "error_on_collision": True,
    }
    with pytest.raises(Exception, match="collision on key 'b'"):
        asyncio.run(_run_rename(params, items))


def test_datetime_format():
    items = [Item(json={"created": "2026-06-14T12:30:00Z"})]
    params = {
        "action": "format",
        "field": "created",
        "format": "%Y-%m-%d",
    }
    out = asyncio.run(_run_datetime(params, items))
    assert out[0].json["created"] == "2026-06-14"


def test_datetime_add_duration():
    items = [Item(json={"ts": "2026-01-01T00:00:00Z"})]
    params = {
        "action": "add",
        "field": "ts",
        "duration": {"value": 1, "unit": "days"},
    }
    out = asyncio.run(_run_datetime(params, items))
    assert out[0].json["ts"] == "2026-01-02T00:00:00Z"


def test_datetime_now_on_empty_input():
    out = asyncio.run(_run_datetime({"action": "now", "field": "ts"}, []))
    assert len(out) == 1
    assert "ts" in out[0].json
