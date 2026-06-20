from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes import parse_csv, parse_json


def test_parse_json_round_trip():
    out = asyncio.run(
        parse_json.run({"input": '{"a":1,"b":[2,3]}'}, input_items=[], context={})
    )
    assert out[0].json["parsed"] == {"a": 1, "b": [2, 3]}


def test_parse_json_malformed():
    with pytest.raises(ValueError, match="invalid JSON"):
        asyncio.run(parse_json.run({"input": "not-json"}, input_items=[], context={}))


def test_parse_csv_with_header():
    text = "id,name\n1,foo\n2,bar\n"
    out = asyncio.run(
        parse_csv.run({"input": text, "has_header": True}, input_items=[], context={})
    )
    assert out[0].json["header"] == ["id", "name"]
    assert out[0].json["rows"] == [
        {"id": "1", "name": "foo"},
        {"id": "2", "name": "bar"},
    ]


def test_parse_csv_without_header():
    text = "1,foo\n2,bar\n"
    out = asyncio.run(
        parse_csv.run({"input": text, "has_header": False}, input_items=[], context={})
    )
    assert out[0].json["header"] is None
    assert out[0].json["rows"] == [["1", "foo"], ["2", "bar"]]
